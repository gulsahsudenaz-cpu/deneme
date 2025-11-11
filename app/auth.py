import secrets, hashlib, time, uuid
from datetime import datetime, timedelta
from fastapi import HTTPException, status, Depends, Header, Request
from sqlalchemy import select, update, delete
from app.db import session_scope
from app.models import AdminOTP, AdminSession
from app.config import settings
from app.logger import logger

def _hash_code(code: str) -> str:
    # salt + sha256
    salt = settings.OTP_HASH_SALT
    return hashlib.sha256((salt + code).encode()).hexdigest()

async def create_otp():
    code = f"{secrets.randbelow(1000000):06d}"
    expires_at = datetime.utcnow() + timedelta(seconds=settings.ADMIN_CODE_TTL_SECONDS)
    async with session_scope() as s:
        s.add(AdminOTP(code_hash=_hash_code(code), expires_at=expires_at))
    return code, expires_at

async def verify_otp_and_issue_session(code: str, client_ip: str = "unknown", user_agent: str = None):
    # Rate limiting: 5 attempts per 15 minutes per IP
    from app.rate_limit import ws_rate_limiter
    ident = f"otp_verify:{client_ip}"
    if not ws_rate_limiter.allow_api(ident, 5/900, 5):  # 5 req per 15 min
        logger.warning(f"OTP verification rate limit exceeded for IP: {client_ip}")
        raise HTTPException(status_code=429, detail="Too many attempts. Please try again later.")
    
    code_hash = _hash_code(code)
    async with session_scope() as s:
        res = await s.execute(
            select(AdminOTP).where(AdminOTP.code_hash==code_hash, AdminOTP.used==False, AdminOTP.expires_at>datetime.utcnow())
        )
        otp = res.scalar_one_or_none()
        if not otp:
            raise HTTPException(status_code=400, detail="Invalid or expired code")
        otp.used = True
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=settings.ADMIN_SESSION_TTL_HOURS)
        # Store user_agent if provided (from request)
        session = AdminSession(token=token, expires_at=expires_at, client_ip=client_ip, user_agent=user_agent)
        s.add(session)
        await s.flush()  # Flush to get session ID
        # Log admin activity (login)
        from app.activity_logger import log_admin_activity
        await log_admin_activity(str(session.id), "login", None, {"ip": client_ip})
        return token, expires_at

async def get_current_admin(
    request: Request,
    authorization: str | None = Header(default=None)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ", 1)[1]
    
    # Check IP whitelist if configured
    if settings.ADMIN_IP_WHITELIST:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else None
        if client_ip and client_ip not in settings.ADMIN_IP_WHITELIST:
            logger.warning(f"Admin access denied for IP: {client_ip}")
            raise HTTPException(status_code=403, detail="Access denied")
    
    async with session_scope() as s:
        res = await s.execute(select(AdminSession).where(AdminSession.token==token, AdminSession.active==True, AdminSession.expires_at>datetime.utcnow()))
        ses = res.scalar_one_or_none()
        if not ses:
            raise HTTPException(status_code=401, detail="Unauthorized")
        
        # Session hijacking protection: Check IP and User-Agent match
        # Get current request IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            current_ip = forwarded_for.split(",")[0].strip()
        else:
            current_ip = request.client.host if request.client else None
        current_user_agent = request.headers.get("user-agent", "")
        
        # Check if IP changed (optional - log warning but don't block if session IP is not set)
        if ses.client_ip and current_ip and ses.client_ip != current_ip:
            logger.warning(f"Session IP mismatch: stored={ses.client_ip}, current={current_ip} for session {ses.id}")
            # Optionally invalidate session for security (uncomment to enable strict mode)
            # await s.execute(update(AdminSession).where(AdminSession.id==ses.id).values(active=False))
            # raise HTTPException(status_code=401, detail="Session invalidated due to IP mismatch")
        
        # Check if User-Agent changed (optional - log warning but don't block)
        if ses.user_agent and current_user_agent and ses.user_agent != current_user_agent:
            logger.warning(f"Session User-Agent mismatch for session {ses.id}: stored={ses.user_agent[:50]}, current={current_user_agent[:50]}")
        
        # Update session IP and User-Agent if not set (first request after login)
        if not ses.client_ip and current_ip:
            await s.execute(update(AdminSession).where(AdminSession.id==ses.id).values(client_ip=current_ip))
        if not ses.user_agent and current_user_agent:
            await s.execute(update(AdminSession).where(AdminSession.id==ses.id).values(user_agent=current_user_agent))
        
        # Update session expiry on activity if refresh enabled
        if settings.SESSION_REFRESH_ENABLED:
            new_expires = datetime.utcnow() + timedelta(hours=settings.ADMIN_SESSION_TTL_HOURS)
            # Token rotation: generate new token and invalidate old one
            new_token = secrets.token_urlsafe(32)
            await s.execute(update(AdminSession).where(AdminSession.id==ses.id).values(
                token=new_token,
                expires_at=new_expires
            ))
            # Return new token in admin dict - endpoint will set response header
            return {"token": new_token, "session_id": str(ses.id), "rotated": True}
        
        return {"token": token, "session_id": str(ses.id), "rotated": False}

async def logout_admin(token: str):
    """Invalidate admin session"""
    async with session_scope() as s:
        await s.execute(update(AdminSession).where(AdminSession.token==token).values(active=False))

async def cleanup_expired_sessions_and_otps():
    """Cleanup expired sessions and used/expired OTPs"""
    try:
        async with session_scope() as s:
            # Delete expired sessions
            await s.execute(delete(AdminSession).where(AdminSession.expires_at < datetime.utcnow()))
            # Delete expired or old used OTPs (older than 1 hour)
            cutoff = datetime.utcnow() - timedelta(hours=1)
            await s.execute(delete(AdminOTP).where(
                (AdminOTP.expires_at < datetime.utcnow()) | 
                ((AdminOTP.used == True) & (AdminOTP.created_at < cutoff))
            ))
        logger.info("Cleaned up expired sessions and OTPs")
    except Exception as e:
        logger.error(f"Error cleaning up expired sessions/OTPs: {e}")

