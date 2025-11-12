from fastapi import FastAPI, Request, Depends, WebSocket, WebSocketDisconnect, Header, HTTPException, Query, status as http_status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware import Middleware
from sqlalchemy import select, func, update, delete, text
import uuid
import asyncio
from datetime import datetime

from app.config import settings
from app.db import init_db, session_scope
from app.models import Conversation, Visitor, Message
from app.schemas import VisitorCreate, AdminLoginRequest, AdminLoginResponse, OTPRequestResponse, SendAdminMessage
from app.auth import create_otp, verify_otp_and_issue_session, get_current_admin, logout_admin, cleanup_expired_sessions_and_otps
from app.activity_logger import log_admin_activity
from app.ws import manager, handle_client, handle_admin
from app.telegram import router as telegram_router
from app.rate_limit import ws_rate_limiter
from app.logger import logger

app = FastAPI(title="Private Support Chat", version="1.0.0")

# Request size limit middleware
class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Check content length header first
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > settings.MAX_REQUEST_SIZE:
                    return JSONResponse(
                        status_code=http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={"error": "Request too large", "detail": f"Maximum request size is {settings.MAX_REQUEST_SIZE} bytes"}
                    )
                # For JSON payloads, also check against JSON limit
                content_type = request.headers.get("content-type", "").lower()
                if "application/json" in content_type and size > settings.MAX_JSON_PAYLOAD_SIZE:
                    return JSONResponse(
                        status_code=http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={"error": "Payload too large", "detail": f"Maximum JSON payload size is {settings.MAX_JSON_PAYLOAD_SIZE} bytes"}
                    )
            except ValueError:
                pass
        
        # For WebSocket, size is checked per message in WebSocket handler
        if request.url.path.startswith("/ws/"):
            return await call_next(request)
        
        # For other requests, let FastAPI handle body parsing
        # Size is already checked via content-length header
        return await call_next(request)

# Security headers (CSP, XSS, HTTPS)
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Force HTTPS in production (skip for health check and WebSocket)
        if settings.FORCE_HTTPS and settings.APP_ENV == "prod" and not request.url.path.startswith("/ws/") and request.url.path != "/health":
            # Check X-Forwarded-Proto header (for reverse proxy)
            proto = request.headers.get("x-forwarded-proto", request.url.scheme)
            if proto != "https":
                # Only redirect if not behind proxy (proxy should handle HTTPS)
                if not request.headers.get("x-forwarded-for"):
                    https_url = str(request.url).replace("http://", "https://", 1)
                    return RedirectResponse(url=https_url, status_code=301)
        
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-XSS-Protection"] = "1; mode=block"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.FORCE_HTTPS and settings.APP_ENV == "prod":
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        csp_origins = ' '.join(settings.ALLOWED_ORIGINS) if settings.ALLOWED_ORIGINS else ''
        resp.headers["Content-Security-Policy"] = f"default-src {settings.CSP_DEFAULT_SRC}; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; font-src 'self' https://cdnjs.cloudflare.com; connect-src 'self' {csp_origins} wss://deneme-sohbet.up.railway.app ws://localhost:* wss: ws:;"
        return resp

# Rate limiting middleware for REST API
class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health check, static files, and WebSocket upgrade
        if request.url.path in ["/health", "/health/detailed", "/", "/admin", "/favicon.ico", "/debug", "/test"] or request.url.path.startswith("/static") or request.url.path.startswith("/ws/"):
            return await call_next(request)
        
        # Get client identifier (use X-Forwarded-For if behind proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        ident = f"api:{client_ip}"
        
        # Rate limit: 100 requests per 5 minutes = ~0.33 req/sec, burst of 10
        rate_per_sec = settings.API_REQ_PER_5MIN / 300  # Convert to per second
        if not ws_rate_limiter.allow_api(ident, rate_per_sec, 10):
            logger.warning(f"Rate limit exceeded for {client_ip} on {request.url.path}")
            return JSONResponse(
                status_code=429,
                content={"error": "Too many requests", "detail": "Rate limit exceeded. Please try again later."},
                headers={"Retry-After": "60"}
            )
        
        return await call_next(request)

# Middleware order matters: Request size limit -> Security headers -> Rate limiting
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],  # Restrict methods
    allow_headers=["Authorization", "Content-Type", "X-Telegram-Bot-Api-Secret-Token"],  # Restrict headers
    expose_headers=["X-New-Token", "X-Token-Rotated"],  # Expose custom headers for token rotation
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
async def startup():
    # Validate environment variables
    try:
        from validate_env import validate_env
        if not validate_env():
            logger.error("Environment validation failed")
            raise RuntimeError("Invalid environment configuration. Please check your .env file.")
        logger.info("Environment validation passed")
    except ImportError:
        logger.warning("validate_env module not found, skipping validation")
    except Exception as e:
        logger.error(f"Environment validation failed: {e}")
        raise RuntimeError("Environment validation failed")
    
    await init_db()
    # Run database migrations
    from app.db import run_migrations
    await run_migrations()
    # Connect to Redis (optional)
    from app.redis_client import redis_client
    await redis_client.connect()
    logger.info("Application started")
    # Start background task for cleanup
    asyncio.create_task(periodic_cleanup())

@app.on_event("shutdown")
async def shutdown():
    # Disconnect from Redis
    from app.redis_client import redis_client
    await redis_client.disconnect()
    logger.info("Application shutdown")

async def periodic_cleanup():
    """Periodic cleanup of expired sessions, OTPs, rate limiter buckets, and cache"""
    cleanup_interval = 3600  # 1 hour, configurable
    max_retries = 3
    
    while True:
        retry_count = 0
        try:
            await asyncio.sleep(cleanup_interval)
            logger.info("Starting periodic cleanup...")
            
            # Cleanup expired sessions and OTPs
            await cleanup_expired_sessions_and_otps()
            
            # Cleanup stale rate limiter buckets
            cleaned = ws_rate_limiter.cleanup_stale_buckets(max_age_minutes=60)
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} stale rate limiter buckets")
            
            # Cleanup expired cache entries
            from app.cache import cache
            expired = cache.cleanup_expired()
            if expired > 0:
                logger.info(f"Cleaned up {expired} expired cache entries")
            
            logger.info("Periodic cleanup completed successfully")
            retry_count = 0  # Reset retry count on success
            
        except Exception as e:
            retry_count += 1
            logger.error(f"Error in periodic cleanup (attempt {retry_count}/{max_retries}): {e}", exc_info=True)
            
            if retry_count >= max_retries:
                logger.critical(f"Periodic cleanup failed after {max_retries} attempts, continuing...")
                retry_count = 0
            
            # Short sleep before retry
            await asyncio.sleep(60)

@app.get("/health")
async def health():
    """Ultra-simple health check for Railway"""
    return {"status": "ok"}

@app.get("/debug")
async def debug_info():
    """Debug endpoint to check file paths"""
    import os
    return {
        "cwd": os.getcwd(),
        "templates_exist": os.path.exists("templates/index.html"),
        "static_exist": os.path.exists("static/js/client.js"),
        "files": os.listdir(".") if os.path.exists(".") else "not found",
        "allowed_origins": settings.ALLOWED_ORIGINS,
        "app_env": settings.APP_ENV,
        "force_https": settings.FORCE_HTTPS
    }

@app.get("/favicon.ico")
async def favicon():
    """Simple favicon response"""
    return Response(content="", media_type="image/x-icon")

@app.get("/ws-test")
async def websocket_test():
    """Test WebSocket endpoint availability"""
    return {
        "websocket_endpoints": ["/ws/client", "/ws/admin"],
        "server_host": "0.0.0.0:8080",
        "websocket_manager": {
            "clients": len(manager.clients),
            "admins": len(manager.admins),
            "max_clients": manager.max_clients,
            "max_admins": manager.max_admins
        },
        "cors_origins": settings.ALLOWED_ORIGINS,
        "instructions": "Try connecting to wss://your-domain/ws/client"
    }

@app.get("/health/detailed")
async def health_detailed():
    """Detailed health check endpoint with system status"""
    from datetime import datetime
    from app.monitoring import SystemMonitor
    
    # Check database connection
    db_status = "ok"
    try:
        async with session_scope() as s:
            await s.execute(select(1))
    except Exception as e:
        db_status = f"error: {str(e)}"
        logger.error(f"Health check database error: {e}")
    
    # Check Redis connection
    redis_status = "ok"
    try:
        from app.redis_client import redis_client
        if redis_client.client:
            await redis_client.client.ping()
        else:
            redis_status = "not_configured"
    except Exception as e:
        redis_status = f"error: {str(e)}"
        logger.warning(f"Health check Redis error: {e}")
    
    # Get system metrics
    try:
        system_health = SystemMonitor.check_system_health()
    except Exception as e:
        logger.error(f"System health check error: {e}")
        system_health = {"status": "error", "error": str(e)}
    
    # Determine overall status
    overall_status = "ok"
    if db_status != "ok":
        overall_status = "critical"
    elif system_health["status"] == "warning" or redis_status != "ok":
        overall_status = "warning"
    
    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "database": db_status,
        "redis": redis_status,
        "websocket_clients": len(manager.clients),
        "websocket_admins": len(manager.admins),
        "system": system_health,
        "version": "2.0.0"
    }

# Templates (simple serve)
@app.get("/", response_class=HTMLResponse)
async def index_page():
    with open("templates/index.html","r",encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    with open("templates/admin.html","r",encoding="utf-8") as f:
        return HTMLResponse(f.read())

# Visitor HTTP API (WebSocket fallback)
@app.post("/api/visitor/join")
async def visitor_join(request: Request):
    data = await request.json()
    display_name = data.get('display_name', 'Ziyaretçi').strip() or 'Ziyaretçi'
    
    async with session_scope() as s:
        v = Visitor(display_name=display_name, client_ip=request.client.host if request.client else None)
        s.add(v)
        await s.flush()
        conv = Conversation(visitor_id=v.id)
        s.add(conv)
        await s.flush()
        conv_id = conv.id
    
    # Notify admin via Telegram
    from app.telegram import notify_new_visitor
    await notify_new_visitor(conv_id, display_name)
    
    return {"conversation_id": str(conv_id), "visitor_name": display_name}

@app.get("/api/visitor/messages/{conversation_id}")
async def visitor_messages(conversation_id: str):
    try:
        conv_id = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")
    
    async with session_scope() as s:
        res = await s.execute(
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at.asc())
            .limit(50)
        )
        messages = res.scalars().all()
        
        return [{
            "id": str(m.id),
            "sender": m.sender,
            "content": m.content,
            "created_at": m.created_at.isoformat()
        } for m in messages]

@app.post("/api/visitor/send")
async def visitor_send(request: Request):
    data = await request.json()
    try:
        conv_id = uuid.UUID(data['conversation_id'])
    except (ValueError, KeyError):
        raise HTTPException(status_code=400, detail="Invalid conversation ID")
    
    content = data.get('content', '').strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content required")
    
    if len(content) > 2000:
        raise HTTPException(status_code=400, detail="Message too long")
    
    async with session_scope() as s:
        # Verify conversation exists
        res = await s.execute(select(Conversation).where(Conversation.id == conv_id, Conversation.status == "open"))
        conv = res.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Save message
        s.add(Message(conversation_id=conv_id, sender="visitor", content=content))
        await s.execute(update(Conversation).where(Conversation.id == conv_id).values(last_activity_at=datetime.utcnow()))
    
    # Notify admin via Telegram
    from app.telegram import notify_visitor_message
    async with session_scope() as s:
        res = await s.execute(select(Visitor).join(Conversation).where(Conversation.id == conv_id))
        visitor = res.scalar_one_or_none()
        if visitor:
            await notify_visitor_message(conv_id, visitor.display_name, content)
    
    return {"ok": True}

# Admin OTP flow
@app.post("/api/admin/request_otp", response_model=OTPRequestResponse)
async def request_otp():
    from app.telegram import tg_send
    try:
        code, expires = await create_otp()
        # send to configured admin chat
        from app.i18n import t
        text = t("admin_login_code", code=code, ttl=settings.ADMIN_CODE_TTL_SECONDS//60)
        await tg_send(settings.TELEGRAM_DEFAULT_CHAT_ID, text)
        logger.info("OTP requested and sent via Telegram")
        return OTPRequestResponse(sent=True)
    except Exception as e:
        # Log error but return sent=False to indicate failure
        logger.error(f"Failed to send OTP via Telegram: {e}", exc_info=True)
        return OTPRequestResponse(sent=False)

@app.post("/api/admin/login", response_model=AdminLoginResponse)
async def admin_login(request: Request, payload: AdminLoginRequest):
    # Get client IP for rate limiting
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"
    
    try:
        user_agent = request.headers.get("user-agent", "")
        token, exp = await verify_otp_and_issue_session(payload.code, client_ip, user_agent)
        logger.info(f"Admin login successful from IP: {client_ip}")
        return AdminLoginResponse(token=token, expires_at=exp)
    except HTTPException:
        logger.warning(f"Admin login failed from IP: {client_ip}")
        raise

# Mark messages as read
@app.post("/api/admin/messages/{message_id}/read")
async def mark_message_read(message_id: str, response: Response, admin=Depends(get_current_admin)):
    # Check if token was rotated and set response header
    if admin.get("rotated") and admin.get("token"):
        response.headers["X-New-Token"] = admin["token"]
        response.headers["X-Token-Rotated"] = "true"
    
    try:
        msg_id = uuid.UUID(message_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid message ID")
    
    async with session_scope() as s:
        # Get conversation_id from message
        res = await s.execute(select(Message).where(Message.id==msg_id))
        msg = res.scalar_one_or_none()
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")
        await s.execute(update(Message).where(Message.id==msg_id).values(read_at=datetime.utcnow()))
    # Log admin activity
    await log_admin_activity(admin["session_id"], "mark_message_read", str(msg.conversation_id), {"message_id": str(msg_id)})
    return {"ok": True}

# Admin REST send (optional alternative to WS)
@app.post("/api/admin/send")
async def admin_send(msg: SendAdminMessage, response: Response, admin=Depends(get_current_admin)):
    # Check if token was rotated and set response header
    if admin.get("rotated") and admin.get("token"):
        response.headers["X-New-Token"] = admin["token"]
        response.headers["X-Token-Rotated"] = "true"
    
    from app.ws import manager, sanitize
    from sqlalchemy import update, select
    from datetime import datetime
    # Sanitize content
    content = sanitize(msg.content)
    if not content:
        raise HTTPException(status_code=400, detail="Message content is required")
    async with session_scope() as s:
        # Verify conversation exists and is open
        res = await s.execute(select(Conversation).where(Conversation.id==msg.conversation_id, Conversation.status=="open"))
        conv = res.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found or closed")
        s.add(Message(conversation_id=msg.conversation_id, sender="admin", content=content))
        await s.execute(update(Conversation).where(Conversation.id==msg.conversation_id).values(last_activity_at=datetime.utcnow()))
    await manager.broadcast_to_conversation(msg.conversation_id, {"type":"message","conversation_id":str(msg.conversation_id),"sender":"admin","content":content})
    # Invalidate cache for conversation list
    from app.cache import cache
    deleted_count = await cache.delete_by_pattern("conversations:*")
    if deleted_count > 0:
        logger.debug(f"Invalidated {deleted_count} conversation list cache entries after admin message")
    # Log admin activity
    await log_admin_activity(admin["session_id"], "send_message", str(msg.conversation_id), {"content_length": len(content)})
    return {"ok": True}

# List conversations (admin) with pagination and caching
@app.get("/api/admin/conversations")
async def list_conversations(request: Request, response: Response, admin=Depends(get_current_admin), limit: int = 50, offset: int = 0):
    # Check if token was rotated and set response header
    if admin.get("rotated") and admin.get("token"):
        response.headers["X-New-Token"] = admin["token"]
        response.headers["X-Token-Rotated"] = "true"
    
    if limit > 100:
        limit = 100
    if limit < 1:
        limit = 50
    
    # Check cache (cache key includes offset and limit)
    from app.cache import cache
    cache_key = f"conversations:{limit}:{offset}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached
    
    async with session_scope() as s:
        # Get conversations with message counts - select only needed columns
        res = await s.execute(
            select(
                Conversation.id,
                Conversation.last_activity_at,
                Visitor.display_name,
                func.coalesce(func.count(Message.id), 0).label('message_count')
            )
            .join(Visitor, Conversation.visitor_id==Visitor.id)
            .outerjoin(Message, Message.conversation_id==Conversation.id)
            .where(Conversation.status=="open")
            .group_by(Conversation.id, Visitor.display_name, Conversation.last_activity_at)
            .order_by(Conversation.last_activity_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = res.all()
        result = [{
            "conversation_id": str(conv_id),
            "visitor_name": visitor_name,
            "last_activity_at": last_activity.isoformat(),
            "message_count": int(msg_count) if msg_count else 0
        } for conv_id, last_activity, visitor_name, msg_count in rows]
        
        # Cache for 30 seconds
        await cache.set(cache_key, result, ttl_seconds=30)
        return result

# List messages of a conversation (admin) with cursor-based pagination
@app.get("/api/admin/messages/{conversation_id}")
async def list_messages(conversation_id: str, response: Response, admin=Depends(get_current_admin), limit: int = 50, cursor: str = None):
    # Check if token was rotated and set response header
    if admin.get("rotated") and admin.get("token"):
        response.headers["X-New-Token"] = admin["token"]
        response.headers["X-Token-Rotated"] = "true"
    
    try:
        conv_id = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")
    if limit > 100:
        limit = 100
    if limit < 1:
        limit = 50
    
    # Check cache for message history
    from app.cache import cache
    cache_key = f"messages:{conversation_id}:{limit}:{cursor or 'none'}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached
    
    async with session_scope() as s:
        # Verify conversation exists and admin has access
        res = await s.execute(select(Conversation).where(Conversation.id==conv_id))
        conv = res.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Cursor-based pagination for better performance
        query = select(Message).where(Message.conversation_id==conv_id)
        
        if cursor:
            try:
                # Parse cursor (timestamp + message ID)
                cursor_parts = cursor.split(":")
                if len(cursor_parts) == 2:
                    cursor_time = datetime.fromisoformat(cursor_parts[0])
                    cursor_id = uuid.UUID(cursor_parts[1])
                    # Get messages after cursor
                    query = query.where(
                        (Message.created_at > cursor_time) | 
                        ((Message.created_at == cursor_time) & (Message.id > cursor_id))
                    )
            except (ValueError, TypeError):
                # Invalid cursor, ignore it
                pass
        
        query = query.order_by(Message.created_at.asc(), Message.id.asc()).limit(limit + 1)
        res = await s.execute(query)
        ms = res.scalars().all()
        
        # Check if there are more messages
        has_more = len(ms) > limit
        if has_more:
            ms = ms[:-1]  # Remove the extra one
        
        # Generate next cursor from last message
        next_cursor = None
        if has_more and ms:
            last_msg = ms[-1]
            next_cursor = f"{last_msg.created_at.isoformat()}:{last_msg.id}"
        
        # Return array format for backward compatibility, but also support cursor
        messages = [{"id":str(m.id),"sender":m.sender,"content":m.content,"created_at":m.created_at.isoformat()} for m in ms]
        
        # If cursor is provided, return new format with pagination info
        if cursor:
            result = {
                "messages": messages,
                "has_more": has_more,
                "next_cursor": next_cursor
            }
        else:
            # Otherwise return simple array for backward compatibility
            result = messages
        
        # Cache message history for 30 seconds
        await cache.set(cache_key, result, ttl_seconds=30)
        
        return result

# Delete conversation (admin)
@app.delete("/api/admin/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, response: Response, admin=Depends(get_current_admin)):
    # Check if token was rotated and set response header
    if admin.get("rotated") and admin.get("token"):
        response.headers["X-New-Token"] = admin["token"]
        response.headers["X-Token-Rotated"] = "true"
    
    from sqlalchemy import delete, select
    try:
        conv_id = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")
    # Delete conversation
    async with session_scope() as s:
        # Verify conversation exists
        res = await s.execute(select(Conversation).where(Conversation.id==conv_id))
        conv = res.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        await s.execute(delete(Conversation).where(Conversation.id==conv_id))
    # Notify both sides AFTER deletion (order matters for cleanup)
    await manager.broadcast_to_conversation(conv_id, {"type":"conversation_deleted","conversation_id":conversation_id})
    # cleanup ws client map (after broadcast so message is delivered)
    await manager.unregister_client(conv_id)
    # Clear cache for conversation list - invalidate all cached pages
    from app.cache import cache
    # Clear all conversation list cache entries by pattern
    deleted_count = await cache.delete_by_pattern("conversations:*")
    if deleted_count > 0:
        logger.info(f"Invalidated {deleted_count} conversation list cache entries")
    logger.info(f"Conversation {conv_id} deleted by admin")
    # Log admin activity
    await log_admin_activity(admin["session_id"], "delete_conversation", str(conv_id), None)
    return {"ok": True}

# Search messages
@app.get("/api/admin/search")
async def search_messages(q: str, response: Response, admin=Depends(get_current_admin), limit: int = 50):
    """Search messages by content"""
    # Check if token was rotated and set response header
    if admin.get("rotated") and admin.get("token"):
        response.headers["X-New-Token"] = admin["token"]
        response.headers["X-Token-Rotated"] = "true"
    
    if not q or len(q) < 2:
        raise HTTPException(status_code=400, detail="Query too short (min 2 chars)")
    
    if limit > 100:
        limit = 100
    
    async with session_scope() as s:
        # Simple LIKE search (can be upgraded to full-text search)
        search_pattern = f"%{q}%"
        res = await s.execute(
            select(Message, Conversation, Visitor)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .join(Visitor, Conversation.visitor_id == Visitor.id)
            .where(Message.content.ilike(search_pattern))
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        results = res.all()
        
        return [{
            "message_id": str(msg.id),
            "conversation_id": str(conv.id),
            "visitor_name": visitor.display_name,
            "sender": msg.sender,
            "content": msg.content,
            "created_at": msg.created_at.isoformat()
        } for msg, conv, visitor in results]

# Statistics dashboard
@app.get("/api/admin/statistics")
async def get_statistics(response: Response, admin=Depends(get_current_admin)):
    """Get dashboard statistics"""
    # Check if token was rotated and set response header
    if admin.get("rotated") and admin.get("token"):
        response.headers["X-New-Token"] = admin["token"]
        response.headers["X-Token-Rotated"] = "true"
    
    async with session_scope() as s:
        # Total conversations
        total_conv = await s.execute(select(func.count(Conversation.id)))
        total_conversations = total_conv.scalar()
        
        # Open conversations
        open_conv = await s.execute(select(func.count(Conversation.id)).where(Conversation.status=="open"))
        open_conversations = open_conv.scalar()
        
        # Total messages
        total_msg = await s.execute(select(func.count(Message.id)))
        total_messages = total_msg.scalar()
        
        # Messages today
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_msg = await s.execute(select(func.count(Message.id)).where(Message.created_at >= today))
        messages_today = today_msg.scalar()
        
        # Average response time (simplified)
        avg_response = await s.execute(
            select(func.avg(Message.created_at - Conversation.created_at))
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Message.sender == "admin")
        )
        avg_response_time = avg_response.scalar()
        
        return {
            "total_conversations": total_conversations or 0,
            "open_conversations": open_conversations or 0,
            "total_messages": total_messages or 0,
            "messages_today": messages_today or 0,
            "avg_response_time_seconds": float(avg_response_time.total_seconds()) if avg_response_time else 0,
            "websocket_clients": len(manager.clients),
            "websocket_admins": len(manager.admins)
        }

# System Test Dashboard
@app.get("/test")
async def test_dashboard():
    with open("templates/test.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/test/comprehensive")
async def comprehensive_system_test():
    """Comprehensive system test - all components"""
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "overall_status": "unknown",
        "tests": {}
    }
    
    # 1. Database Tests
    db_tests = {}
    try:
        async with session_scope() as s:
            # Basic connection
            await s.execute(select(1))
            db_tests["connection"] = {"status": "✅ PASS", "message": "Database connection successful"}
            
            # Table existence
            tables = ["visitors", "conversations", "messages", "admin_otps", "admin_sessions", "telegram_links", "admin_activity_logs", "conversation_tags"]
            for table in tables:
                try:
                    await s.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
                    db_tests[f"table_{table}"] = {"status": "✅ PASS", "message": f"Table {table} exists and accessible"}
                except Exception as e:
                    db_tests[f"table_{table}"] = {"status": "❌ FAIL", "message": f"Table {table} error: {str(e)}"}
            
            # CRUD operations test
            try:
                # Create test visitor
                test_visitor = Visitor(display_name="Test User", client_ip="127.0.0.1")
                s.add(test_visitor)
                await s.flush()
                
                # Create test conversation
                test_conv = Conversation(visitor_id=test_visitor.id)
                s.add(test_conv)
                await s.flush()
                
                # Create test message
                test_msg = Message(conversation_id=test_conv.id, sender="visitor", content="Test message")
                s.add(test_msg)
                await s.flush()
                
                # Read test
                result = await s.execute(select(Message).where(Message.id == test_msg.id))
                msg = result.scalar_one()
                
                # Update test
                await s.execute(update(Message).where(Message.id == test_msg.id).values(content="Updated test message"))
                
                # Delete test (cascade will handle related records)
                await s.execute(delete(Conversation).where(Conversation.id == test_conv.id))
                
                db_tests["crud_operations"] = {"status": "✅ PASS", "message": "CRUD operations successful"}
            except Exception as e:
                db_tests["crud_operations"] = {"status": "❌ FAIL", "message": f"CRUD error: {str(e)}"}
                
    except Exception as e:
        db_tests["connection"] = {"status": "❌ FAIL", "message": f"Database connection failed: {str(e)}"}
    
    results["tests"]["database"] = db_tests
    
    # 2. Redis/Cache Tests
    cache_tests = {}
    try:
        from app.cache import cache
        # Test cache operations
        await cache.set("test_key", "test_value", 60)
        cached_value = await cache.get("test_key")
        if cached_value == "test_value":
            cache_tests["cache_operations"] = {"status": "✅ PASS", "message": "Cache set/get successful"}
        else:
            cache_tests["cache_operations"] = {"status": "❌ FAIL", "message": "Cache value mismatch"}
        await cache.delete("test_key")
        
        # Test Redis connection
        from app.redis_client import redis_client
        if redis_client.enabled and redis_client.client:
            try:
                await redis_client.client.ping()
                cache_tests["redis_connection"] = {"status": "✅ PASS", "message": "Redis connection active"}
            except:
                cache_tests["redis_connection"] = {"status": "⚠️ WARN", "message": "Redis configured but not responding"}
        else:
            cache_tests["redis_connection"] = {"status": "ℹ️ INFO", "message": "Redis not configured, using in-memory fallback"}
    except Exception as e:
        cache_tests["cache_operations"] = {"status": "❌ FAIL", "message": f"Cache error: {str(e)}"}
    
    results["tests"]["cache"] = cache_tests
    
    # 3. Telegram Tests
    telegram_tests = {}
    try:
        from app.telegram import tg_send
        # Test Telegram API (without actually sending)
        if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_DEFAULT_CHAT_ID:
            telegram_tests["config"] = {"status": "✅ PASS", "message": "Telegram configuration present"}
            # Test API endpoint availability
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getMe")
                if r.status_code == 200:
                    bot_info = r.json()
                    telegram_tests["bot_api"] = {"status": "✅ PASS", "message": f"Bot API active: {bot_info['result']['username']}"}
                else:
                    telegram_tests["bot_api"] = {"status": "❌ FAIL", "message": f"Bot API error: {r.status_code}"}
        else:
            telegram_tests["config"] = {"status": "❌ FAIL", "message": "Telegram configuration missing"}
    except Exception as e:
        telegram_tests["bot_api"] = {"status": "❌ FAIL", "message": f"Telegram API error: {str(e)}"}
    
    results["tests"]["telegram"] = telegram_tests
    
    # 4. WebSocket Manager Tests
    ws_tests = {}
    try:
        from app.ws import manager
        ws_tests["manager_init"] = {"status": "✅ PASS", "message": f"WebSocket manager active - Clients: {len(manager.clients)}, Admins: {len(manager.admins)}"}
        ws_tests["connection_limits"] = {"status": "✅ PASS", "message": f"Limits: {manager.max_clients} clients, {manager.max_admins} admins"}
    except Exception as e:
        ws_tests["manager_init"] = {"status": "❌ FAIL", "message": f"WebSocket manager error: {str(e)}"}
    
    results["tests"]["websocket"] = ws_tests
    
    # 5. Rate Limiter Tests
    rate_tests = {}
    try:
        from app.rate_limit import ws_rate_limiter
        # Test rate limiter
        test_id = "test_client_123"
        if ws_rate_limiter.allow_ws(test_id, 1, 5):
            rate_tests["rate_limiter"] = {"status": "✅ PASS", "message": "Rate limiter functioning"}
        else:
            rate_tests["rate_limiter"] = {"status": "❌ FAIL", "message": "Rate limiter blocking unexpectedly"}
    except Exception as e:
        rate_tests["rate_limiter"] = {"status": "❌ FAIL", "message": f"Rate limiter error: {str(e)}"}
    
    results["tests"]["rate_limiting"] = rate_tests
    
    # 6. Authentication Tests
    auth_tests = {}
    try:
        from app.auth import create_otp, _hash_code
        # Test OTP generation
        code, expires = await create_otp()
        if len(code) == 6 and code.isdigit():
            auth_tests["otp_generation"] = {"status": "✅ PASS", "message": "OTP generation successful"}
        else:
            auth_tests["otp_generation"] = {"status": "❌ FAIL", "message": "OTP format invalid"}
        
        # Test hash function
        test_hash = _hash_code("123456")
        if len(test_hash) == 64:  # SHA256 hex length
            auth_tests["hash_function"] = {"status": "✅ PASS", "message": "Hash function working"}
        else:
            auth_tests["hash_function"] = {"status": "❌ FAIL", "message": "Hash function invalid"}
    except Exception as e:
        auth_tests["otp_generation"] = {"status": "❌ FAIL", "message": f"Auth error: {str(e)}"}
    
    results["tests"]["authentication"] = auth_tests
    
    # 7. Environment Tests
    env_tests = {}
    required_vars = ["DATABASE_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_DEFAULT_CHAT_ID", "TELEGRAM_WEBHOOK_SECRET", "OTP_HASH_SALT", "ALLOWED_ORIGINS"]
    for var in required_vars:
        if hasattr(settings, var) and getattr(settings, var):
            env_tests[f"env_{var.lower()}"] = {"status": "✅ PASS", "message": f"{var} configured"}
        else:
            env_tests[f"env_{var.lower()}"] = {"status": "❌ FAIL", "message": f"{var} missing"}
    
    results["tests"]["environment"] = env_tests
    
    # 8. System Resources Tests
    system_tests = {}
    try:
        from app.monitoring import SystemMonitor
        metrics = SystemMonitor.get_system_metrics()
        if "error" not in metrics:
            system_tests["system_metrics"] = {"status": "✅ PASS", "message": f"CPU: {metrics['cpu_percent']}%, Memory: {metrics['memory_percent']}%"}
            system_tests["disk_space"] = {"status": "✅ PASS", "message": f"Disk: {metrics['disk_percent']}% used, {metrics['disk_free_gb']}GB free"}
        else:
            system_tests["system_metrics"] = {"status": "❌ FAIL", "message": f"Metrics error: {metrics['error']}"}
    except Exception as e:
        system_tests["system_metrics"] = {"status": "❌ FAIL", "message": f"System monitoring error: {str(e)}"}
    
    results["tests"]["system"] = system_tests
    
    # 9. File System Tests
    file_tests = {}
    critical_files = [
        "app/main.py", "app/models.py", "app/ws.py", "app/auth.py", "app/telegram.py",
        "static/js/admin.js", "static/js/client.js", "static/js/utils.js",
        "templates/admin.html", "templates/index.html", "requirements.txt"
    ]
    
    for file_path in critical_files:
        try:
            with open(file_path, 'r') as f:
                content = f.read()
                if len(content) > 0:
                    file_tests[f"file_{file_path.replace('/', '_').replace('.', '_')}"] = {"status": "✅ PASS", "message": f"{file_path} exists ({len(content)} chars)"}
                else:
                    file_tests[f"file_{file_path.replace('/', '_').replace('.', '_')}"] = {"status": "❌ FAIL", "message": f"{file_path} empty"}
        except Exception as e:
            file_tests[f"file_{file_path.replace('/', '_').replace('.', '_')}"] = {"status": "❌ FAIL", "message": f"{file_path} missing or error: {str(e)}"}
    
    results["tests"]["filesystem"] = file_tests
    
    # Calculate overall status
    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    
    for category in results["tests"].values():
        for test in category.values():
            total_tests += 1
            if "✅ PASS" in test["status"]:
                passed_tests += 1
            elif "❌ FAIL" in test["status"]:
                failed_tests += 1
    
    if failed_tests == 0:
        results["overall_status"] = "✅ ALL SYSTEMS OPERATIONAL"
    elif failed_tests < total_tests * 0.2:  # Less than 20% failed
        results["overall_status"] = "⚠️ MOSTLY OPERATIONAL"
    else:
        results["overall_status"] = "❌ SYSTEM ISSUES DETECTED"
    
    results["summary"] = {
        "total_tests": total_tests,
        "passed": passed_tests,
        "failed": failed_tests,
        "warnings": total_tests - passed_tests - failed_tests,
        "success_rate": f"{(passed_tests/total_tests*100):.1f}%" if total_tests > 0 else "0%"
    }
    
    return results

# Admin logout
@app.post("/api/admin/logout")
async def admin_logout(response: Response, admin=Depends(get_current_admin)):
    # Check if token was rotated and set response header (though logout doesn't need it)
    if admin.get("rotated") and admin.get("token"):
        response.headers["X-New-Token"] = admin["token"]
        response.headers["X-Token-Rotated"] = "true"
    
    token = admin["token"]
    await logout_admin(token)
    logger.info(f"Admin session {admin['session_id']} logged out")
    # Log admin activity
    await log_admin_activity(admin["session_id"], "logout", None, None)
    return {"ok": True}

# Telegram webhook
app.include_router(telegram_router, prefix="")

# WebSockets
@app.websocket("/ws/client")
async def ws_client(ws: WebSocket):
    logger.info(f"WebSocket client endpoint hit - Headers: {dict(ws.headers)}")
    logger.info(f"Client info: {ws.client}")
    try:
        await handle_client(ws)
    except WebSocketDisconnect:
        logger.info("Client WebSocket disconnected normally")
    except Exception as e:
        logger.error(f"Error in client WebSocket handler: {e}", exc_info=True)
        try:
            await ws.close(code=1011, reason="Internal error")
        except (WebSocketDisconnect, ConnectionError):
            # Connection already closed
            pass
        except Exception as close_error:
            logger.error(f"Error closing WebSocket after error: {close_error}")

@app.websocket("/ws/admin")
async def ws_admin(ws: WebSocket, authorization: str | None = Header(default=None), token: str | None = Query(default=None)):
    logger.info(f"WebSocket admin endpoint hit - Headers: {dict(ws.headers)}")
    logger.info(f"Client info: {ws.client}")
    logger.info(f"Authorization header: {authorization}")
    logger.info(f"Token query param: {token[:10] if token else None}...")
    
    # Accept connection first (WebSocket protocol requirement)
    await ws.accept()
    logger.info("Admin WebSocket connection accepted")
    
    # Check IP whitelist if configured
    if settings.ADMIN_IP_WHITELIST:
        client_ip = ws.client.host if ws.client else None
        if client_ip and client_ip not in settings.ADMIN_IP_WHITELIST:
            logger.warning(f"Admin WebSocket access denied for IP: {client_ip}")
            await ws.close(code=1008, reason="IP not allowed")
            return
    
    # accept token via header or query (browser can't set WS headers)
    auth_token = None
    if authorization and authorization.startswith("Bearer "):
        auth_token = authorization.split(" ", 1)[1]
    elif token:
        auth_token = token
    else:
        await ws.close(code=1008, reason="Missing token")
        return
    # validate token after accepting (WebSocket doesn't support Request dependency easily)
    try:
        # Validate token directly
        async with session_scope() as s:
            from app.models import AdminSession
            res = await s.execute(select(AdminSession).where(AdminSession.token==auth_token, AdminSession.active==True, AdminSession.expires_at>datetime.utcnow()))
            ses = res.scalar_one_or_none()
            if not ses:
                raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        await ws.close(code=1008, reason="Invalid token")
        return
    # Token is valid, now handle the connection
    try:
        await handle_admin(ws, auth_token)
    except WebSocketDisconnect:
        # Normal disconnect, no need to log
        pass
    except Exception as e:
        logger.error(f"Error in admin WebSocket handler: {e}", exc_info=True)
        try:
            await ws.close(code=1011, reason="Internal error")
        except (WebSocketDisconnect, ConnectionError):
            # Connection already closed
            pass
        except Exception as close_error:
            logger.error(f"Error closing WebSocket after error: {close_error}")

