import logging
import sys
import re
from app.config import settings

class SensitiveDataFilter(logging.Filter):
    """Filter to mask sensitive data in logs"""
    PATTERNS = [
        (re.compile(r'(token["\s:=]+)([\w\-_]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(password["\s:=]+)([\w\-_]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(secret["\s:=]+)([\w\-_]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(api[_\s]?key["\s:=]+)([\w\-_]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(authorization["\s:=]+bearer\s+)([\w\-_]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(\d{6})', re.IGNORECASE), r'***OTP***'),  # OTP codes
    ]
    
    def filter(self, record):
        message = record.getMessage()
        for pattern, replacement in self.PATTERNS:
            message = pattern.sub(replacement, message)
        record.msg = message
        record.args = ()
        return True

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.APP_ENV == "prod" else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)

logger = logging.getLogger("support_chat")
logger.addFilter(SensitiveDataFilter())

