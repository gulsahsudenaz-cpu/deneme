from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
import os

class Settings(BaseSettings):
    APP_ENV: str = "dev"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    ALLOWED_ORIGINS: List[str] = []

    DATABASE_URL: str

    SESSION_IDLE_MINUTES: int = 30
    ADMIN_CODE_TTL_SECONDS: int = 300
    ADMIN_SESSION_TTL_HOURS: int = 24

    WS_USER_MSGS_PER_SEC: int = 1
    WS_USER_BURST: int = 5
    API_REQ_PER_5MIN: int = 100

    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_DEFAULT_CHAT_ID: str
    TELEGRAM_WEBHOOK_SECRET: str

    CSP_DEFAULT_SRC: str = "'self'"
    MAX_MESSAGE_LEN: int = 2000

    # Database pool settings
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30

    # Security
    OTP_HASH_SALT: str  # REQUIRED - Must be set in .env (min 32 chars)
    FORCE_HTTPS: bool = True  # Set to False in dev
    CSRF_SECRET_KEY: str = ""  # Optional - CSRF protection secret key (min 32 chars if set)
    CSRF_ENABLED: bool = False  # Enable CSRF protection (optional, Bearer token already provides protection)
    
    # Request size limits
    MAX_REQUEST_SIZE: int = 1024 * 1024  # 1MB
    MAX_WS_MESSAGE_SIZE: int = 64 * 1024  # 64KB
    MAX_JSON_PAYLOAD_SIZE: int = 512 * 1024  # 512KB
    
    # IP Whitelisting (optional, comma-separated)
    ADMIN_IP_WHITELIST: List[str] = []  # Empty = no whitelist
    TELEGRAM_WEBHOOK_IP_WHITELIST: List[str] = []  # Empty = no whitelist (Telegram IPs should be validated)
    
    # Session management
    SESSION_IDLE_TIMEOUT_MINUTES: int = 30  # Idle timeout for sessions
    SESSION_REFRESH_ENABLED: bool = True  # Enable session refresh on activity
    
    # WebSocket connection limits
    WS_MAX_CLIENTS: int = 250   # Maximum concurrent client connections
    WS_MAX_ADMINS: int = 5      # Maximum concurrent admin connections
    
    # Cache settings
    CACHE_MAX_SIZE: int = 1000  # Maximum cache entries
    CACHE_DEFAULT_TTL: int = 300  # Default cache TTL in seconds
    
    # Redis (optional)
    REDIS_URL: str = ""  # Empty = disabled, use in-memory fallback
    
    @field_validator('DB_POOL_SIZE', 'DB_MAX_OVERFLOW')
    @classmethod
    def validate_pool_size(cls, v):
        if v < 1:
            raise ValueError('Pool size must be at least 1')
        if v > 100:
            raise ValueError('Pool size too large (max 100)')
        return v
    
    @field_validator('WS_MAX_CLIENTS', 'WS_MAX_ADMINS')
    @classmethod
    def validate_ws_limits(cls, v):
        if v < 1:
            raise ValueError('WebSocket limit must be at least 1')
        if v > 10000:
            raise ValueError('WebSocket limit too large (max 10000)')
        return v

    class Config:
        env_file = ".env"
        case_sensitive = False

def get_settings() -> Settings:
    s = Settings()
    
    # Validate OTP_HASH_SALT
    if len(s.OTP_HASH_SALT) < 32:
        raise ValueError("OTP_HASH_SALT must be at least 32 characters long")
    if s.OTP_HASH_SALT == "change-me-in-production":
        raise ValueError("OTP_HASH_SALT must be changed from default value")
    
    # Validate DATABASE_URL format
    if not s.DATABASE_URL.startswith(('postgresql://', 'postgresql+asyncpg://')):
        raise ValueError('DATABASE_URL must start with postgresql:// or postgresql+asyncpg://')
    
    # Validate REDIS_URL format (if set)
    if s.REDIS_URL and not s.REDIS_URL.startswith(('redis://', 'rediss://')):
        raise ValueError('REDIS_URL must start with redis:// or rediss://')
    
    # Validate CSRF_SECRET_KEY (if CSRF_ENABLED is True)
    if s.CSRF_ENABLED and s.CSRF_SECRET_KEY:
        if len(s.CSRF_SECRET_KEY) < 32:
            raise ValueError("CSRF_SECRET_KEY must be at least 32 characters long if CSRF_ENABLED is True")
    
    # Parse ALLOWED_ORIGINS from env (comma-separated string)
    raw = os.getenv("ALLOWED_ORIGINS", "")
    if raw:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        s.ALLOWED_ORIGINS = origins
    # Parse ADMIN_IP_WHITELIST from env
    raw = os.getenv("ADMIN_IP_WHITELIST", "")
    if raw:
        s.ADMIN_IP_WHITELIST = [ip.strip() for ip in raw.split(",") if ip.strip()]
    # Parse TELEGRAM_WEBHOOK_IP_WHITELIST from env
    raw = os.getenv("TELEGRAM_WEBHOOK_IP_WHITELIST", "")
    if raw:
        s.TELEGRAM_WEBHOOK_IP_WHITELIST = [ip.strip() for ip in raw.split(",") if ip.strip()]
    return s

settings = get_settings()

