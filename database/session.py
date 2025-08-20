from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from fastapi import Request
from core.config import settings 
from sqlalchemy import text # Make sure this import is present



Base = declarative_base()

async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_factory = request.app.state.db_session_factory
    session: AsyncSession = session_factory()
    try:
        yield session
    except Exception as e:
        await session.rollback()
        raise e
    finally:
        await session.close()