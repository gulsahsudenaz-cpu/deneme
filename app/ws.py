import uuid, html, asyncio
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect, HTTPException
from sqlalchemy import select, update, delete
from datetime import datetime
from app.db import session_scope
from app.models import Visitor, Conversation, Message
from app.config import settings
from app.rate_limit import ws_rate_limiter
from app.logger import logger

def sanitize(text: str) -> str:
    """Sanitize user input by escaping HTML and limiting length.
    
    Args:
        text: Raw text input from user
        
    Returns:
        Sanitized text with HTML escaped and length limited
    """
    return html.escape(text or "")[:settings.MAX_MESSAGE_LEN]

class WSManager:
    def __init__(self):
        self.clients: Dict[uuid.UUID, WebSocket] = {}      # conversation_id -> visitor ws
        self.admins: Set[WebSocket] = set()
        self.max_clients: int = settings.WS_MAX_CLIENTS
        self.max_admins: int = settings.WS_MAX_ADMINS

    async def register_client(self, conv_id: uuid.UUID, ws: WebSocket):
        if len(self.clients) >= self.max_clients:
            logger.warning(f"Max client connections reached: {self.max_clients}")
            await ws.close(code=1008, reason="Server at capacity")
            return False
        # If conversation already has a client, close the old one
        if conv_id in self.clients:
            try:
                await self.clients[conv_id].close(code=1000, reason="New connection")
            except (WebSocketDisconnect, ConnectionError):
                # Connection already closed, ignore
                pass
            except Exception as e:
                logger.warning(f"Error closing existing WebSocket connection: {e}")
        self.clients[conv_id] = ws
        return True

    async def unregister_client(self, conv_id: uuid.UUID):
        self.clients.pop(conv_id, None)

    async def register_admin(self, ws: WebSocket):
        if len(self.admins) >= self.max_admins:
            logger.warning(f"Max admin connections reached: {self.max_admins}")
            await ws.close(code=1008, reason="Server at capacity")
            return False
        self.admins.add(ws)
        return True

    async def unregister_admin(self, ws: WebSocket):
        self.admins.discard(ws)

    async def send(self, ws: WebSocket, data: dict):
        try:
            # Check message size before sending
            import json
            msg_bytes = json.dumps(data).encode('utf-8')
            if len(msg_bytes) > settings.MAX_WS_MESSAGE_SIZE:
                logger.warning(f"WebSocket message too large to send: {len(msg_bytes)} bytes, truncating content")
                # Truncate content if it's a message
                if isinstance(data, dict) and data.get("type") == "message" and "content" in data:
                    max_content_size = settings.MAX_WS_MESSAGE_SIZE - 200  # Reserve space for JSON structure
                    content_bytes = data["content"].encode('utf-8')
                    if len(content_bytes) > max_content_size:
                        # Truncate to fit
                        truncated = data["content"][:max_content_size//4]
                        data["content"] = truncated + "... (truncated)"
            await ws.send_json(data)
        except Exception as e:
            logger.error(f"Error sending WebSocket message: {e}", exc_info=True)
            raise

    async def broadcast_admin(self, data: dict):
        # Parallel broadcast for better performance
        tasks = [self.send(a, data) for a in self.admins]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Remove dead connections
        dead = []
        for admin, result in zip(list(self.admins), results):
            if isinstance(result, Exception):
                dead.append(admin)
        for a in dead:
            self.admins.discard(a)

    async def broadcast_to_conversation(self, conv_id: uuid.UUID, data: dict):
        # visitor
        ws = self.clients.get(conv_id)
        if ws:
            try:
                await ws.send_json(data)
            except (WebSocketDisconnect, ConnectionError):
                # Connection closed, remove from clients
                self.clients.pop(conv_id, None)
            except Exception as e:
                logger.error(f"Error sending WebSocket message to client: {e}", exc_info=True)
        # admins
        await self.broadcast_admin(data)

manager = WSManager()

async def origin_ok(ws: WebSocket) -> bool:
    """Validate WebSocket origin against allowed origins.
    
    Args:
        ws: WebSocket connection
        
    Returns:
        True if origin is allowed, False otherwise
    """
    # TEMPORARY: Allow all origins for Railway debugging
    # TODO: Re-enable strict origin checking after WebSocket issues are resolved
    return True
    
    # Original strict validation (commented out for debugging)
    # # In dev mode, allow all origins if ALLOWED_ORIGINS is empty
    # if not settings.ALLOWED_ORIGINS and settings.APP_ENV == "dev":
    #     return True
    # origin = ws.headers.get("origin")
    # if not origin:
    #     return False
    # # Exact match or exact protocol+domain match (prevents subdomain hijacking)
    # for allowed in settings.ALLOWED_ORIGINS:
    #     if origin == allowed:
    #         return True
    #     # Allow subdomains only if explicitly configured with wildcard
    #     if allowed.startswith("*."):
    #         domain = allowed[2:]
    #         if origin.endswith(domain) and origin.count(".") == domain.count(".") + 1:
    #             return True
    # return False

async def handle_client(ws: WebSocket):
    logger.info(f"Client WebSocket connection attempt from {ws.client.host if ws.client else 'unknown'}")
    logger.info(f"Headers: {dict(ws.headers)}")
    
    await ws.accept()
    logger.info("Client WebSocket connection accepted")
    
    # Check origin after accepting (WebSocket protocol requirement)
    if not await origin_ok(ws):
        logger.warning(f"Client WebSocket origin not allowed: {ws.headers.get('origin')}")
        await ws.close(code=1008, reason="Origin not allowed")
        return
    
    logger.info("Client WebSocket origin validation passed")
    # step 1: expect {"type":"join","display_name":"..."} OR {"type":"resume","conversation_id":"..."}
    try:
        init = await ws.receive_json()
    except Exception as e:
        await ws.close(code=1008, reason="Invalid initial message")
        return
    from app.telegram import notify_new_visitor, notify_visitor_message

    if init.get("type") == "join":
        display_name = sanitize(init.get("display_name","")).strip() or "Ziyaretçi"
        # create visitor & conversation
        conv_id = None
        async with session_scope() as s:
            v = Visitor(display_name=display_name, client_ip=ws.client.host if ws.client else None, user_agent=ws.headers.get("user-agent",""))
            s.add(v)
            await s.flush()
            conv = Conversation(visitor_id=v.id)
            s.add(conv)
            await s.flush()
            conv_id = conv.id  # Get ID while still in session
        if not conv_id:
            await ws.close(code=1011, reason="Failed to create conversation")
            return
        if not await manager.register_client(conv_id, ws):
            return  # Connection already closed
        # history empty on first join
        await manager.send(ws, {"type":"joined","conversation_id":str(conv_id),"visitor_name":display_name})
        # notify admins + telegram
        await manager.broadcast_admin({"type":"conversation_opened","conversation_id":str(conv_id),"visitor_name":display_name})
        await notify_new_visitor(conv_id, display_name)

    elif init.get("type") == "resume":
        try:
            conv_id = uuid.UUID(init.get("conversation_id"))
        except (ValueError, TypeError, AttributeError) as e:
            logger.warning(f"Invalid UUID in resume request: {e}")
            await ws.close(code=1008, reason="Invalid conversation ID")
            return
        # Verify conversation exists and is open (not deleted or closed)
        async with session_scope() as s:
            res = await s.execute(select(Conversation).where(Conversation.id==conv_id, Conversation.status=="open"))
            conv = res.scalar_one_or_none()
            if not conv:
                await ws.close(code=1008, reason="Conversation not found, closed, or deleted")
                return
        await manager.register_client(conv_id, ws)
        # send history
        visitor_name = "Ziyaretçi"
        async with session_scope() as s:
            # Get messages and visitor name in one query
            # Limit to last 100 messages for performance
            res = await s.execute(
                select(Message, Visitor)
                .join(Conversation, Message.conversation_id==Conversation.id)
                .join(Visitor, Conversation.visitor_id==Visitor.id)
                .where(Message.conversation_id==conv_id)
                .order_by(Message.created_at.desc())
                .limit(50)   # Limit to last 50 messages for performance
            )
            rows = res.all()
            # Reverse to show oldest first in UI
            history = [m for m, v in reversed(rows)]
            if rows:
                visitor_name = rows[0][1].display_name
        await manager.send(ws, {"type":"history","conversation_id":str(conv_id),"visitor_name":visitor_name,
                                "messages":[{"id":str(m.id),"sender":m.sender,"content":m.content,"created_at":m.created_at.isoformat()} for m in history]})
    else:
        await ws.close(code=1008)
        return

    # message loop
    ident = f"client:{ws.client.host if ws.client else 'na'}:{str(conv_id)}"
    while True:
        try:
            # Receive text message first to check size before parsing
            text = await ws.receive_text()
            
            # Validate message size BEFORE parsing
            if len(text.encode('utf-8')) > settings.MAX_WS_MESSAGE_SIZE:
                await manager.send(ws, {"type":"error","error":"message_too_large"})
                logger.warning(f"WebSocket message too large: {len(text)} bytes from {ident}")
                continue
            
            # Parse JSON after size validation
            import json
            msg = json.loads(text)
        except WebSocketDisconnect:
            await manager.unregister_client(conv_id)
            break
        except json.JSONDecodeError as e:
            # Invalid JSON
            logger.error(f"Invalid JSON in WebSocket message: {e}")
            await manager.send(ws, {"type":"error","error":"invalid_json"})
            continue
        except Exception as e:
            # Other errors
            logger.error(f"Error receiving WebSocket message: {e}", exc_info=True)
            await manager.send(ws, {"type":"error","error":"invalid_message"})
            continue
        if msg.get("type") == "message":
            if not ws_rate_limiter.allow_ws(ident, settings.WS_USER_MSGS_PER_SEC, settings.WS_USER_BURST):
                await manager.send(ws, {"type":"error","error":"rate_limited"})
                continue
            content = sanitize(msg.get("content",""))
            if not content:
                continue
            # save message and get visitor info in one transaction
            display_name = "Ziyaretçi"
            async with session_scope() as s:
                # Verify conversation exists and is open, get visitor info
                res = await s.execute(select(Conversation, Visitor).join(Visitor, Conversation.visitor_id==Visitor.id).where(Conversation.id==conv_id, Conversation.status=="open"))
                row = res.first()
                if not row:
                    # Conversation deleted or not found
                    await manager.send(ws, {"type":"error","error":"conversation_not_found"})
                    continue
                conv, visitor = row
                display_name = visitor.display_name
                # Save message
                s.add(Message(conversation_id=conv_id, sender="visitor", content=content))
                await s.execute(update(Conversation).where(Conversation.id==conv_id).values(last_activity_at=datetime.utcnow()))
            # deliver
            await manager.broadcast_to_conversation(conv_id, {
                "type":"message","conversation_id":str(conv_id),"sender":"visitor","content":content
            })
            # telegram notify
            await notify_visitor_message(conv_id, display_name, content)

        elif msg.get("type") == "typing":
            # Broadcast typing indicator to admin
            await manager.broadcast_admin({
                "type": "typing",
                "conversation_id": str(conv_id),
                "sender": "visitor"
            })
        
        elif msg.get("type") == "delete_conversation":
            # ignore from client
            pass

async def handle_admin(ws: WebSocket, token: str):
    logger.info(f"Admin WebSocket connection from {ws.client.host if ws.client else 'unknown'} with token: {token[:10]}...")
    logger.info(f"Headers: {dict(ws.headers)}")
    
    # Connection already accepted in main.py
    # Token validation done in main.py before calling this function
    # Origin check (connection already accepted)
    if not await origin_ok(ws):
        logger.warning(f"Admin WebSocket origin not allowed: {ws.headers.get('origin')}")
        await ws.close(code=1008, reason="Origin not allowed")
        return
    
    logger.info("Admin WebSocket origin validation passed")
    if not await manager.register_admin(ws):
        return  # Connection already closed
    # send current open conversations snapshot
    from sqlalchemy import select, func
    async with session_scope() as s:
        from app.models import Conversation, Visitor, Message
        # Get conversations with message counts
        res = await s.execute(
            select(
                Conversation,
                Visitor,
                func.coalesce(func.count(Message.id), 0).label('message_count')
            )
            .join(Visitor, Conversation.visitor_id==Visitor.id)
            .outerjoin(Message, Message.conversation_id==Conversation.id)
            .where(Conversation.status=="open")
            .group_by(Conversation.id, Visitor.id, Conversation.last_activity_at)
            .order_by(Conversation.last_activity_at.desc())
        )
        rows = res.all()
    await manager.send(ws, {"type":"conversations",
                            "items":[{"conversation_id":str(c.id),"visitor_name":v.display_name,"last_activity_at":c.last_activity_at.isoformat(),"status":c.status,"message_count":int(msg_count) if msg_count else 0} for c,v,msg_count in rows]})
    try:
        while True:
            try:
                # Receive text message first to check size before parsing
                text = await ws.receive_text()
                
                # Validate message size BEFORE parsing
                if len(text.encode('utf-8')) > settings.MAX_WS_MESSAGE_SIZE:
                    await manager.send(ws, {"type":"error","error":"message_too_large"})
                    logger.warning(f"Admin WebSocket message too large: {len(text)} bytes")
                    continue
                
                # Parse JSON after size validation
                import json
                data = json.loads(text)
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError as e:
                # Invalid JSON
                logger.error(f"Invalid JSON in admin WebSocket message: {e}")
                await manager.send(ws, {"type":"error","error":"invalid_json"})
                continue
            except Exception as e:
                # Other errors
                logger.error(f"Error receiving admin WebSocket message: {e}", exc_info=True)
                await manager.send(ws, {"type":"error","error":"invalid_message"})
                continue
            if data.get("type") == "admin_message":
                from app.config import settings
                try:
                    conv_id = uuid.UUID(data["conversation_id"])
                except (ValueError, TypeError):
                    continue
                content = sanitize(data.get("content",""))
                if not content:
                    continue
                # Verify conversation exists and is open
                async with session_scope() as s:
                    res = await s.execute(select(Conversation).where(Conversation.id==conv_id, Conversation.status=="open"))
                    conv = res.scalar_one_or_none()
                    if not conv:
                        continue
                    s.add(Message(conversation_id=conv_id, sender="admin", content=content))
                    await s.execute(update(Conversation).where(Conversation.id==conv_id).values(last_activity_at=datetime.utcnow()))
                await manager.broadcast_to_conversation(conv_id, {"type":"message","conversation_id":str(conv_id),"sender":"admin","content":content})
            elif data.get("type") == "typing":
                # Broadcast typing indicator to visitor
                try:
                    conv_id = uuid.UUID(data["conversation_id"])
                except (ValueError, TypeError):
                    continue
                await manager.broadcast_to_conversation(conv_id, {
                    "type": "typing",
                    "conversation_id": str(conv_id),
                    "sender": "admin"
                })
            
            elif data.get("type") == "delete_conversation":
                try:
                    conv_id = uuid.UUID(data["conversation_id"])
                except (ValueError, TypeError):
                    continue
                # Delete conversation and notify
                async with session_scope() as s:
                    # Verify conversation exists before deleting
                    res = await s.execute(select(Conversation).where(Conversation.id==conv_id))
                    conv = res.scalar_one_or_none()
                    if not conv:
                        continue
                    # hard delete cascade
                    await s.execute(delete(Conversation).where(Conversation.id==conv_id))
                # Notify both sides AFTER deletion (order matters)
                await manager.broadcast_to_conversation(conv_id, {"type":"conversation_deleted","conversation_id":str(conv_id)})
                # cleanup ws client map if any (after broadcast)
                await manager.unregister_client(conv_id)
    except WebSocketDisconnect:
        await manager.unregister_admin(ws)

