#!/usr/bin/env python3
"""Environment validation script for production deployment"""

import os
import sys
from urllib.parse import urlparse

def validate_env():
    """Validate required environment variables"""
    required_vars = [
        'DATABASE_URL',
        'TELEGRAM_BOT_TOKEN', 
        'TELEGRAM_DEFAULT_CHAT_ID',
        'TELEGRAM_WEBHOOK_SECRET',
        'OTP_HASH_SALT',
        'ALLOWED_ORIGINS'
    ]
    
    missing = []
    warnings = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    # Validate DATABASE_URL format
    db_url = os.getenv('DATABASE_URL')
    if db_url:
        try:
            parsed = urlparse(db_url)
            if not all([parsed.scheme, parsed.hostname, parsed.username]):
                warnings.append("DATABASE_URL format may be invalid")
        except Exception:
            warnings.append("DATABASE_URL format is invalid")
    
    # Check OTP salt length
    salt = os.getenv('OTP_HASH_SALT')
    if salt and len(salt) < 32:
        warnings.append("OTP_HASH_SALT should be at least 32 characters")
    
    # Check HTTPS enforcement
    if os.getenv('APP_ENV') == 'prod' and os.getenv('FORCE_HTTPS') != 'true':
        warnings.append("FORCE_HTTPS should be 'true' in production")
    
    # Results
    if missing:
        print("❌ Missing required environment variables:")
        for var in missing:
            print(f"  - {var}")
        return False
    
    if warnings:
        print("⚠️  Environment warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    
    print("✅ Environment validation passed!")
    return True

if __name__ == "__main__":
    # Load .env if exists
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    if not validate_env():
        sys.exit(1)