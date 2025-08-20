# DANGER
# THIS SCRIPT DELETES THE ENTIRE DATABASE AND RECREATES ALL TABLES
# NEVER RUN THIS ON A PRODUCTION DATABASE
import asyncio
from core.config import settings

from sqlalchemy.ext.asyncio import create_async_engine
import logging
from database.models import *  # Import all models to ensure they are registered with SQLAlchemy !!!IMPORTANT
from database.session import Base 

engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False
    )

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Starting script...")
logger.info("Database url is:", settings.DATABASE_URL)
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
   print("WARNING: THIS SCRIPT WILL DELETE ALL DATA IN THE DATABASE AND RECREATE ALL TABLES.")
   print("you need to uncomment the last line to run this script.")
#    asyncio.run(create_tables())