import motor.motor_asyncio
from beanie import init_beanie
import os
from dotenv import load_dotenv
from app.models import User, PythonJob, ActivityLog

# Load environment variables
load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "ubuntucontrolpanel")


async def init_db():
    """Initialize database connection and Beanie ODM"""
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URL)
    await init_beanie(
        database=client[DB_NAME],
        document_models=[
            User,
            PythonJob,
            ActivityLog,
        ]
    )
    return client 