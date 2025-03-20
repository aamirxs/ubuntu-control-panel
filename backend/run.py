import os
import uvicorn
import asyncio
from dotenv import load_dotenv
from app.init_admin import init_admin_user

# Load environment variables
load_dotenv()

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))


async def startup():
    """Run startup tasks"""
    # Initialize admin user
    await init_admin_user()


if __name__ == "__main__":
    # Run startup tasks
    asyncio.run(startup())
    
    # Start the server
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=True,
        log_level="info"
    ) 