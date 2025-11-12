import uuid
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings
from app.logger import logger

class Base(DeclarativeBase):
    pass

engine_kwargs = {
    "future": True,
    "pool_pre_ping": True,
    "echo": False  # Set to True for SQL query logging in dev
}

if settings.DATABASE_URL.startswith(("postgresql://", "postgresql+asyncpg://")):
    engine_kwargs.update(
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT
    )

engine = create_async_engine(
    settings.DATABASE_URL,
    **engine_kwargs
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

@asynccontextmanager
async def session_scope():
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database error: {e}", exc_info=True)
            raise

async def init_db():
    # create tables if not exist
    from app import models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def run_migrations():
    """Run database migrations from migrations/ directory"""
    from pathlib import Path
    from sqlalchemy import text
    
    migration_dir = Path("migrations")
    if not migration_dir.exists():
        logger.info("Migrations directory not found, skipping migrations")
        return
    
    # Get all SQL migration files sorted by name
    migration_files = sorted([f for f in migration_dir.glob("*.sql")])
    if not migration_files:
        logger.info("No migration files found")
        return
    
    # Read and execute migration files
    async with engine.begin() as conn:
        for migration_file in migration_files:
            try:
                logger.info(f"Running migration: {migration_file.name}")
                with open(migration_file, "r", encoding="utf-8") as f:
                    sql = f.read()
                # Execute migration SQL using text() for raw SQL
                # Split by semicolon and execute each statement
                statements = [s.strip() for s in sql.split(";") if s.strip() and not s.strip().startswith("--")]
                for statement in statements:
                    if statement:
                        try:
                            await conn.execute(text(statement))
                        except Exception as stmt_error:
                            # Check if error is because table/column already exists (migration already run)
                            error_msg = str(stmt_error).lower()
                            if "already exists" in error_msg or "duplicate" in error_msg or "duplicate key" in error_msg:
                                logger.info(f"Migration statement already applied, skipping: {statement[:50]}...")
                            else:
                                # Re-raise if it's a different error
                                raise
                logger.info(f"Migration {migration_file.name} executed successfully")
            except Exception as e:
                # Log error but don't fail startup
                error_msg = str(e).lower()
                if "already exists" in error_msg or "duplicate" in error_msg:
                    logger.info(f"Migration {migration_file.name} already applied, skipping")
                else:
                    logger.error(f"Migration {migration_file.name} failed: {e}")
                    # Don't raise - allow app to start even if migration fails
                    # raise  # Uncomment to fail on migration error
