"""Pytest package initialization"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("OTP_HASH_SALT", "x" * 32)
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_DEFAULT_CHAT_ID", "123456789")
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost")
os.environ.setdefault("APP_ENV", "test")
