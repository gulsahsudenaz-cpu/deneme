"""Admin activity logging"""
import uuid
import json
from datetime import datetime
from app.db import session_scope
from app.models import AdminActivityLog
from app.logger import logger

async def log_admin_activity(
    session_id: str,
    action: str,
    conversation_id: str = None,
    details: dict = None
):
    """Log admin activity to database"""
    try:
        async with session_scope() as s:
            log_entry = AdminActivityLog(
                session_id=uuid.UUID(session_id),
                action=action,
                conversation_id=uuid.UUID(conversation_id) if conversation_id else None,
                details=json.dumps(details) if details else None
            )
            s.add(log_entry)
    except Exception as e:
        logger.error(f"Failed to log admin activity: {e}")
