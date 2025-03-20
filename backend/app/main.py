from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocket
import uvicorn
import os
import logging
from typing import List

# Import routers
from app.routers import auth, files, terminal, python_deployer, dashboard, users

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Ubuntu Control Panel",
    description="Advanced web-based hosting control panel for Ubuntu 24.04 LTS servers",
    version="1.0.0",
)

# Configure CORS
origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://localhost",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(files.router, prefix="/api/files", tags=["File Manager"])
app.include_router(terminal.router, prefix="/api/terminal", tags=["Terminal"])
app.include_router(python_deployer.router, prefix="/api/python", tags=["Python Deployer"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# WebSocket connection manager
connected_websockets: List[WebSocket] = []

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.append(websocket)
    try:
        while True:
            # Wait for messages
            data = await websocket.receive_text()
            # Process websocket messages here
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        connected_websockets.remove(websocket)

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "Ubuntu Control Panel"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 