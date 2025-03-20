import asyncio
import os
from dotenv import load_dotenv
import logging
from app.database import init_db
from app.models import User, UserRole
from app.routers.auth import get_password_hash

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")


async def init_admin_user():
    """Initialize admin user if it doesn't exist"""
    await init_db()
    
    # Check if admin user exists
    admin_user = await User.find_one({"role": UserRole.ADMIN})
    
    if not admin_user:
        logger.info("Creating default admin user")
        
        # Create admin user
        hashed_password = get_password_hash(ADMIN_PASSWORD)
        admin_user = User(
            username=ADMIN_USERNAME,
            email=ADMIN_EMAIL,
            hashed_password=hashed_password,
            role=UserRole.ADMIN
        )
        await admin_user.save()
        
        logger.info(f"Admin user '{ADMIN_USERNAME}' created successfully")
    else:
        logger.info(f"Admin user '{admin_user.username}' already exists")


if __name__ == "__main__":
    asyncio.run(init_admin_user()) 