from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from typing import List, Dict, Any, Optional
import os
import shutil
import aiofiles
import zipfile
import io
from datetime import datetime
from pathlib import Path

from app.models import User
from app.routers.auth import get_current_user
from app.services.logging import log_activity

router = APIRouter()

# Base directory for all file operations
BASE_DIR = os.getenv("FILES_BASE_DIR", "/home")


def get_user_dir(username: str) -> str:
    """Get the user's home directory"""
    user_dir = os.path.join(BASE_DIR, username)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir


async def is_safe_path(path: str, user_dir: str) -> bool:
    """Check if the path is within the user's directory (no path traversal)"""
    # Get absolute paths
    abs_path = os.path.abspath(path)
    abs_user_dir = os.path.abspath(user_dir)
    
    # Check if the path is within the user's directory
    return abs_path.startswith(abs_user_dir)


@router.get("/list")
async def list_files(
    request: Request,
    current_user: User = Depends(get_current_user),
    path: str = ""
):
    """List files and directories at the specified path"""
    user_dir = get_user_dir(current_user.username)
    target_path = os.path.join(user_dir, path)
    
    if not await is_safe_path(target_path, user_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this path"
        )
    
    if not os.path.exists(target_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Path not found"
        )
    
    if not os.path.isdir(target_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is not a directory"
        )
    
    # List files and directories
    items = []
    for item in os.listdir(target_path):
        item_path = os.path.join(target_path, item)
        stats = os.stat(item_path)
        items.append({
            "name": item,
            "path": os.path.join(path, item).replace("\\", "/"),
            "is_dir": os.path.isdir(item_path),
            "size": stats.st_size,
            "modified": datetime.fromtimestamp(stats.st_mtime).isoformat()
        })
    
    await log_activity(
        current_user.username,
        "list_files",
        request.client.host,
        f"Listed directory: {path}"
    )
    
    return {
        "items": items,
        "current_path": path
    }


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    request: Request = None,
    current_user: User = Depends(get_current_user),
    path: str = ""
):
    """Upload a file to the specified path"""
    user_dir = get_user_dir(current_user.username)
    target_dir = os.path.join(user_dir, path)
    
    if not await is_safe_path(target_dir, user_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this path"
        )
    
    if not os.path.exists(target_dir):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Path not found"
        )
    
    if not os.path.isdir(target_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is not a directory"
        )
    
    # Create the file
    file_path = os.path.join(target_dir, file.filename)
    
    async with aiofiles.open(file_path, "wb") as f:
        # Read file in chunks to handle large files
        while content := await file.read(1024 * 1024):  # 1MB chunks
            await f.write(content)
    
    await log_activity(
        current_user.username,
        "upload_file",
        request.client.host,
        f"Uploaded file: {os.path.join(path, file.filename)}"
    )
    
    return {
        "message": "File uploaded successfully",
        "filename": file.filename,
        "path": os.path.join(path, file.filename).replace("\\", "/")
    }


@router.get("/download")
async def download_file(
    path: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Download a file from the specified path"""
    user_dir = get_user_dir(current_user.username)
    file_path = os.path.join(user_dir, path)
    
    if not await is_safe_path(file_path, user_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this path"
        )
    
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    if os.path.isdir(file_path):
        # For directories, create a zip file
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(file_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, os.path.dirname(file_path))
                    zf.write(full_path, rel_path)
        
        memory_file.seek(0)
        
        dir_name = os.path.basename(file_path)
        
        await log_activity(
            current_user.username,
            "download_dir",
            request.client.host,
            f"Downloaded directory as zip: {path}"
        )
        
        return StreamingResponse(
            memory_file,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={dir_name}.zip"}
        )
    else:
        # For regular files
        await log_activity(
            current_user.username,
            "download_file",
            request.client.host,
            f"Downloaded file: {path}"
        )
        
        return FileResponse(
            file_path,
            filename=os.path.basename(file_path)
        )


@router.post("/mkdir")
async def create_directory(
    path: str,
    name: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Create a new directory"""
    user_dir = get_user_dir(current_user.username)
    parent_dir = os.path.join(user_dir, path)
    
    if not await is_safe_path(parent_dir, user_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this path"
        )
    
    if not os.path.exists(parent_dir):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent directory not found"
        )
    
    if not os.path.isdir(parent_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parent path is not a directory"
        )
    
    new_dir = os.path.join(parent_dir, name)
    if os.path.exists(new_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Directory already exists"
        )
    
    os.makedirs(new_dir)
    
    await log_activity(
        current_user.username,
        "create_directory",
        request.client.host,
        f"Created directory: {os.path.join(path, name)}"
    )
    
    return {
        "message": "Directory created successfully",
        "path": os.path.join(path, name).replace("\\", "/")
    }


@router.delete("/delete")
async def delete_item(
    path: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Delete a file or directory"""
    user_dir = get_user_dir(current_user.username)
    item_path = os.path.join(user_dir, path)
    
    if not await is_safe_path(item_path, user_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this path"
        )
    
    if not os.path.exists(item_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Path not found"
        )
    
    # Get the type before deletion for logging
    is_directory = os.path.isdir(item_path)
    
    try:
        if is_directory:
            shutil.rmtree(item_path)
        else:
            os.remove(item_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete: {str(e)}"
        )
    
    action = "delete_directory" if is_directory else "delete_file"
    await log_activity(
        current_user.username,
        action,
        request.client.host,
        f"Deleted {'directory' if is_directory else 'file'}: {path}"
    )
    
    return {
        "message": f"{'Directory' if is_directory else 'File'} deleted successfully",
        "path": path
    }


@router.post("/rename")
async def rename_item(
    path: str,
    new_name: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Rename a file or directory"""
    user_dir = get_user_dir(current_user.username)
    item_path = os.path.join(user_dir, path)
    
    if not await is_safe_path(item_path, user_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this path"
        )
    
    if not os.path.exists(item_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Path not found"
        )
    
    # Get parent directory
    parent_dir = os.path.dirname(item_path)
    new_path = os.path.join(parent_dir, new_name)
    
    if os.path.exists(new_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A file or directory with this name already exists"
        )
    
    try:
        os.rename(item_path, new_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rename: {str(e)}"
        )
    
    # Get new relative path
    parent_rel_path = os.path.dirname(path)
    new_rel_path = os.path.join(parent_rel_path, new_name).replace("\\", "/")
    
    is_directory = os.path.isdir(new_path)
    await log_activity(
        current_user.username,
        "rename_item",
        request.client.host,
        f"Renamed {'directory' if is_directory else 'file'} from {path} to {new_rel_path}"
    )
    
    return {
        "message": f"{'Directory' if is_directory else 'File'} renamed successfully",
        "old_path": path,
        "new_path": new_rel_path
    }


@router.post("/move")
async def move_item(
    source_path: str,
    target_path: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Move a file or directory to another location"""
    user_dir = get_user_dir(current_user.username)
    source_full_path = os.path.join(user_dir, source_path)
    target_full_path = os.path.join(user_dir, target_path)
    
    # Make sure target path is a directory
    if os.path.exists(target_full_path) and not os.path.isdir(target_full_path):
        target_dir = os.path.dirname(target_full_path)
    else:
        target_dir = target_full_path
    
    # Check if paths are safe
    if not await is_safe_path(source_full_path, user_dir) or not await is_safe_path(target_dir, user_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this path"
        )
    
    if not os.path.exists(source_full_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source path not found"
        )
    
    if not os.path.exists(os.path.dirname(target_full_path)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target directory not found"
        )
    
    # Get basename of source
    source_name = os.path.basename(source_full_path)
    dest_path = os.path.join(target_dir, source_name)
    
    if os.path.exists(dest_path) and source_full_path != dest_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A file or directory with this name already exists at the destination"
        )
    
    try:
        # Create the destination directory if it doesn't exist
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.move(source_full_path, dest_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to move: {str(e)}"
        )
    
    is_directory = os.path.isdir(dest_path)
    await log_activity(
        current_user.username,
        "move_item",
        request.client.host,
        f"Moved {'directory' if is_directory else 'file'} from {source_path} to {target_path}"
    )
    
    return {
        "message": f"{'Directory' if is_directory else 'File'} moved successfully",
        "source_path": source_path,
        "target_path": os.path.join(target_path, source_name).replace("\\", "/")
    }


@router.get("/content")
async def get_file_content(
    path: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Get the content of a text file"""
    user_dir = get_user_dir(current_user.username)
    file_path = os.path.join(user_dir, path)
    
    if not await is_safe_path(file_path, user_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this path"
        )
    
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    if os.path.isdir(file_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is a directory, not a file"
        )
    
    # Check if file is text
    try:
        # Try to read a small chunk of the file
        with open(file_path, 'r', encoding='utf-8', errors='strict') as f:
            f.read(4096)  # Read up to 4KB
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not a text file"
        )
    
    # If we got here, file is valid text, read it
    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
        content = await f.read()
    
    await log_activity(
        current_user.username,
        "read_file",
        request.client.host,
        f"Read file content: {path}"
    )
    
    return {
        "content": content,
        "path": path
    }


@router.post("/content")
async def update_file_content(
    path: str,
    content: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Update the content of a text file"""
    user_dir = get_user_dir(current_user.username)
    file_path = os.path.join(user_dir, path)
    
    if not await is_safe_path(file_path, user_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this path"
        )
    
    # Create the directory if it doesn't exist
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
        await f.write(content)
    
    await log_activity(
        current_user.username,
        "update_file",
        request.client.host,
        f"Updated file content: {path}"
    )
    
    return {
        "message": "File updated successfully",
        "path": path
    }


@router.post("/extract")
async def extract_archive(
    extract_to: Optional[str] = None,
    request: Request = None,
    current_user: User = Depends(get_current_user),
    archive_path: str = ""
):
    """Extract a zip archive"""
    user_dir = get_user_dir(current_user.username)
    archive_full_path = os.path.join(user_dir, archive_path)
    
    if not await is_safe_path(archive_full_path, user_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this path"
        )
    
    if not os.path.exists(archive_full_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Archive not found"
        )
    
    # Determine extract path
    if extract_to:
        extract_path = os.path.join(user_dir, extract_to)
    else:
        extract_path = os.path.dirname(archive_full_path)
    
    if not await is_safe_path(extract_path, user_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to extraction path"
        )
    
    try:
        os.makedirs(extract_path, exist_ok=True)
        with zipfile.ZipFile(archive_full_path, 'r') as zip_ref:
            # Make sure all paths in the zip are safe
            for file in zip_ref.namelist():
                target_file_path = os.path.join(extract_path, file)
                if not await is_safe_path(target_file_path, user_dir):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Dangerous path in zip file: {file}"
                    )
            
            # Extract all files
            zip_ref.extractall(extract_path)
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid zip file"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract archive: {str(e)}"
        )
    
    await log_activity(
        current_user.username,
        "extract_archive",
        request.client.host,
        f"Extracted archive {archive_path} to {extract_to or os.path.dirname(archive_path)}"
    )
    
    return {
        "message": "Archive extracted successfully",
        "archive_path": archive_path,
        "extract_path": extract_to or os.path.dirname(archive_path)
    } 