import httpx, uuid, asyncio
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import select
from ipaddress import ip_address, ip_network
from app.config import settings
from app.db import session_scope
from app.models import Conversation, Message, TelegramLink
from datetime import datetime
from app.logger import logger

router = APIRouter()

TELEGRAM_API = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"
TELEGRAM_IP_RANGES = ["149.154.160.0/20", "91.108.4.0/22"]

def is_telegram_ip(ip: str) -> bool:
    """Validate if IP is from Telegram's official IP ranges"""
    try:
        ip_obj = ip_address(ip)
        return any(ip_obj in ip_network(range) for range in TELEGRAM_IP_RANGES)
    except (ValueError, TypeError):
        return False

async def tg_send(chat_id: int | str, text: str, reply_to_message_id: int | None = None, retries: int = 3):
    """Send Telegram message with retry logic and exponential backoff with jitter"""
    import random
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                payload = {"chat_id": chat_id, "text": text}
                if reply_to_message_id:
                    payload["reply_to_message_id"] = reply_to_message_id
                    payload["allow_sending_without_reply"] = True
                r = await client.post(f"{TELEGRAM_API}/sendMessage", json=payload)
                r.raise_for_status()
                data = r.json()
                return data["result"]["message_id"]
        except httpx.HTTPError as e:
            if attempt == retries - 1:
                raise
            # Exponential backoff with jitter: 2^attempt + random(0-1)
            backoff = (2 ** attempt) + random.random()
            logger.warning(f"Telegram API error (attempt {attempt + 1}/{retries}): {e}, retrying in {backoff:.2f}s")
            await asyncio.sleep(backoff)
    raise Exception("Failed to send Telegram message after retries")

async def notify_new_visitor(conv_id: uuid.UUID, visitor_name: str):
    from app.i18n import t
    text = t("new_visitor", name=visitor_name, conv_id=str(conv_id))
    try:
        msg_id = await tg_send(settings.TELEGRAM_DEFAULT_CHAT_ID, text)
        async with session_scope() as s:
            s.add(TelegramLink(conversation_id=conv_id, tg_chat_id=int(settings.TELEGRAM_DEFAULT_CHAT_ID), tg_message_id=msg_id))
    except Exception as e:
        # Log error but don't fail the request
        logger.error(f"Failed to send Telegram notification: {e}", exc_info=True)

async def notify_visitor_message(conv_id: uuid.UUID, visitor_name: str, content: str):
    from app.i18n import t
    # Truncate content if too long for Telegram (max 4096 chars, but we limit to 2000)
    # Content is already sanitized, so safe to send
    text = t("visitor_message", name=visitor_name, content=content, conv_id=str(conv_id))
    # Telegram has a 4096 character limit, but we're already limiting to 2000
    if len(text) > 4096:
        text = text[:4090] + "..."
    # Find last link for reply threading (if any)
    async with session_scope() as s:
        res = await s.execute(select(TelegramLink).where(TelegramLink.conversation_id==conv_id).order_by(TelegramLink.created_at.desc()))
        link = res.scalars().first()
    reply_to = link.tg_message_id if link else None
    try:
        msg_id = await tg_send(settings.TELEGRAM_DEFAULT_CHAT_ID, text, reply_to_message_id=reply_to)
        # Save new TelegramLink for this message to maintain reply chain
        async with session_scope() as s:
            s.add(TelegramLink(conversation_id=conv_id, tg_chat_id=int(settings.TELEGRAM_DEFAULT_CHAT_ID), tg_message_id=msg_id))
    except Exception as e:
        # Log error but don't fail the request
        logger.error(f"Failed to send Telegram notification: {e}", exc_info=True)

@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    # Verify shared secret
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != settings.TELEGRAM_WEBHOOK_SECRET:
        logger.warning("Telegram webhook: Invalid secret token")
        raise HTTPException(status_code=403, detail="Bad secret")
    
    # Get client IP
    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() if request.headers.get("X-Forwarded-For") else (request.client.host if request.client else None)
    
    # Validate Telegram IP (official IP ranges)
    if client_ip and not is_telegram_ip(client_ip):
        logger.warning(f"Telegram webhook: Invalid IP (not from Telegram): {client_ip}")
        raise HTTPException(status_code=403, detail="Invalid IP")
    
    # IP whitelist check (optional, additional security)
    if settings.TELEGRAM_WEBHOOK_IP_WHITELIST:
        if client_ip and client_ip not in settings.TELEGRAM_WEBHOOK_IP_WHITELIST:
            logger.warning(f"Telegram webhook: Access denied for IP: {client_ip}")
            raise HTTPException(status_code=403, detail="Access denied")
    data = await request.json()
    msg = data.get("message") or data.get("edited_message")
    if not msg:
        return {"ok": True}
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()
    if not text:
        return {"ok": True}
    reply = msg.get("reply_to_message")
    if not reply:
        # Require reply chain to route to conversation
        # Optionally parse UUID in text (advanced)
        return {"ok": True}

    reply_msg_id = reply["message_id"]
    # map reply_to_message to conversation
    async with session_scope() as s:
        res = await s.execute(select(TelegramLink).where(TelegramLink.tg_chat_id==chat_id, TelegramLink.tg_message_id==reply_msg_id))
        link = res.scalar_one_or_none()
        if not link:
            return {"ok": True}
        conv_id = link.conversation_id
        # Verify conversation is open
        conv_res = await s.execute(select(Conversation).where(Conversation.id==conv_id, Conversation.status=="open"))
        conv = conv_res.scalar_one_or_none()
        if not conv:
            return {"ok": True}
        # Sanitize and validate text content
        from app.ws import sanitize
        content = sanitize(text)
        if not content:
            return {"ok": True}
        # Save message as admin/telegram
        from datetime import datetime
        from sqlalchemy import update
        m = Message(conversation_id=conv_id, sender="admin", content=content)
        s.add(m)
        await s.execute(update(Conversation).where(Conversation.id==conv_id).values(last_activity_at=datetime.utcnow()))
    # Broadcast to participants via WS (import locally to avoid cycle)
    from app.ws import manager
    await manager.broadcast_to_conversation(conv_id, {
        "type":"message",
        "conversation_id": str(conv_id),
        "sender":"admin",
        "content": content,
        "via":"telegram"
    })
    return {"ok": True}

