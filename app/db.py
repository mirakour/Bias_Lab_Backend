import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

DATABASE_URL = os.getenv("DATABASE_URL", "")
# Switch driver to asyncpg if a plain postgres URL is provided
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Render Postgres internal URL works without SSL. If you use the EXTERNAL URL,
# uncomment the next line:
# DATABASE_URL += "?sslmode=require"

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db():
    async with SessionLocal() as session:
        yield session
