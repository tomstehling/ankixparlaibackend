import asyncio
import logging

from database.session import Base, engine 

from database.models import User, Note, Card, ChatMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Starting script...")
async def create_tables():

    logger.info("Creating database tables...")
    conn = await engine.connect()
    logger.info("Connected to the database.")
    try:
        await conn.begin()
        logger.warning("dropping all tables...")
        await conn.run_sync(Base.metadata.drop_all)
        logger.info("Creating all tables...")
        await conn.run_sync(Base.metadata.create_all)
        await conn.commit()
    except Exception as e:
        await conn.rollback()
        logger.error(f"Error creating database tables: {e}")
        raise
    finally:
        await conn.close()
        logger.info("Database tables created successfully.")
        await engine.dispose()
if __name__ == "__main__":
    asyncio.run(create_tables())