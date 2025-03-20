from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Request
import asyncio
import asyncssh
import json
import os
import pwd
from typing import Dict, List, Optional

from app.models import User
from app.routers.auth import get_current_user
from app.services.logging import log_activity

router = APIRouter()

# Store active terminal sessions
active_sessions: Dict[str, asyncio.subprocess.Process] = {}


@router.websocket("/ws/{username}")
async def terminal_websocket(
    websocket: WebSocket,
    username: str
):
    """WebSocket endpoint for terminal sessions"""
    await websocket.accept()
    
    # Authentication for WebSocket
    try:
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=1008, reason="Missing authentication token")
            return
        
        # Validate token and get user (this would be handled by your auth system)
        # For example, you might call a function similar to get_current_user
        # Since websocket connections can't use Depends, we have to handle auth here
        from app.routers.auth import jwt, SECRET_KEY, ALGORITHM, get_user
        
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            token_username = payload.get("sub")
            if not token_username or token_username != username:
                await websocket.close(code=1008, reason="Invalid authentication")
                return
            
            user = await get_user(username)
            if not user:
                await websocket.close(code=1008, reason="User not found")
                return
        except Exception:
            await websocket.close(code=1008, reason="Invalid authentication")
            return
        
        # Create a new terminal session
        session_id = f"{username}_{id(websocket)}"
        
        # Start process
        user_dir = f"/home/{username}"
        os.makedirs(user_dir, exist_ok=True)
        
        # Spawn bash process
        process = await asyncio.create_subprocess_exec(
            "bash",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=user_dir
        )
        
        active_sessions[session_id] = process
        
        # Log the activity
        # We can't use the normal request object here, so we'll get client IP from websocket
        client_ip = websocket.client.host
        await log_activity(username, "terminal_connect", client_ip, f"Terminal session started: {session_id}")
        
        # Create tasks for reading from process and from websocket
        read_task = asyncio.create_task(
            read_from_process(websocket, process, session_id)
        )
        write_task = asyncio.create_task(
            write_to_process(websocket, process, session_id)
        )
        
        try:
            # Wait for either task to complete
            done, pending = await asyncio.wait(
                [read_task, write_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel the other task
            for task in pending:
                task.cancel()
        except Exception as e:
            print(f"Error in terminal session: {e}")
        finally:
            # Clean up the session
            if session_id in active_sessions:
                process.terminate()
                del active_sessions[session_id]
            
            await websocket.close()
            await log_activity(username, "terminal_disconnect", client_ip, f"Terminal session ended: {session_id}")
    
    except WebSocketDisconnect:
        # Handle client disconnect
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")


async def read_from_process(
    websocket: WebSocket,
    process: asyncio.subprocess.Process,
    session_id: str
):
    """Read output from process and send to WebSocket"""
    try:
        while True:
            line = await process.stdout.read(1024)
            if not line:
                break
            
            await websocket.send_text(line.decode())
    except asyncio.CancelledError:
        # Task was cancelled, that's okay
        pass
    except Exception as e:
        print(f"Error reading from process: {e}")


async def write_to_process(
    websocket: WebSocket,
    process: asyncio.subprocess.Process,
    session_id: str
):
    """Read messages from WebSocket and write to process"""
    try:
        while True:
            message = await websocket.receive_text()
            
            # Check for special commands
            if message.startswith("__RESIZE:"):
                # Handle terminal resize
                try:
                    _, cols, rows = message.split(":")
                    # If using a proper PTY, you would resize it here
                    continue
                except Exception:
                    pass
            
            # Write the command to the process
            process.stdin.write(message.encode())
            await process.stdin.drain()
    except asyncio.CancelledError:
        # Task was cancelled, that's okay
        pass
    except Exception as e:
        print(f"Error writing to process: {e}")


@router.post("/kill/{session_id}")
async def kill_terminal_session(
    session_id: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Kill a terminal session (admin or owner only)"""
    # Extract username from session_id
    try:
        username = session_id.split("_")[0]
    except IndexError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session ID format"
        )
    
    # Check if user is admin or session owner
    if current_user.username != username and not current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to kill this session"
        )
    
    # Kill the session
    if session_id in active_sessions:
        process = active_sessions[session_id]
        process.terminate()
        del active_sessions[session_id]
        
        await log_activity(
            current_user.username,
            "kill_terminal",
            request.client.host,
            f"Killed terminal session: {session_id}"
        )
        
        return {"message": "Terminal session terminated"}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Terminal session not found"
        )


@router.get("/sessions")
async def list_terminal_sessions(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """List active terminal sessions"""
    # If the user is admin, return all sessions
    # Otherwise, return only the user's sessions
    if current_user.role == "admin":
        sessions = list(active_sessions.keys())
    else:
        sessions = [
            session_id for session_id in active_sessions.keys()
            if session_id.startswith(f"{current_user.username}_")
        ]
    
    await log_activity(
        current_user.username,
        "list_terminal_sessions",
        request.client.host,
        "Listed terminal sessions"
    )
    
    return {"sessions": sessions} 