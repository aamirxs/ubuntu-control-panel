from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
import os
import subprocess
import sys
import shutil
import aiofiles
import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
import re

from app.models import User
from app.routers.auth import get_current_user
from app.services.logging import log_activity
from app.routers.files import get_user_dir, is_safe_path

router = APIRouter()


@router.post("/upload_script")
async def upload_script(
    file: UploadFile = File(...),
    request: Request = None,
    current_user: User = Depends(get_current_user),
    path: str = ""
):
    """Upload a Python script"""
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
    
    # Check file extension
    if not file.filename.endswith('.py'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Python scripts (.py) are allowed"
        )
    
    # Create the file
    file_path = os.path.join(target_dir, file.filename)
    
    async with aiofiles.open(file_path, "wb") as f:
        # Read file in chunks to handle large files
        while content := await file.read(1024 * 1024):  # 1MB chunks
            await f.write(content)
    
    await log_activity(
        current_user.username,
        "upload_script",
        request.client.host,
        f"Uploaded Python script: {os.path.join(path, file.filename)}"
    )
    
    return {
        "message": "Script uploaded successfully",
        "filename": file.filename,
        "path": os.path.join(path, file.filename).replace("\\", "/")
    }


@router.post("/create_virtualenv")
async def create_virtual_environment(
    script_path: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Create a virtual environment for a script"""
    user_dir = get_user_dir(current_user.username)
    full_script_path = os.path.join(user_dir, script_path)
    
    if not await is_safe_path(full_script_path, user_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this path"
        )
    
    if not os.path.exists(full_script_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Script not found"
        )
    
    # Get script directory
    script_dir = os.path.dirname(full_script_path)
    venv_path = os.path.join(script_dir, '.venv')
    
    # Check if venv already exists
    if os.path.exists(venv_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Virtual environment already exists for this script"
        )
    
    try:
        # Create venv
        result = subprocess.run(
            [sys.executable, '-m', 'venv', venv_path],
            capture_output=True,
            text=True,
            check=True
        )
        
        await log_activity(
            current_user.username,
            "create_virtualenv",
            request.client.host,
            f"Created virtual environment for: {script_path}"
        )
        
        return {
            "message": "Virtual environment created successfully",
            "venv_path": venv_path.replace(user_dir, '').replace("\\", "/").lstrip('/'),
            "script_path": script_path
        }
        
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create virtual environment: {e.stderr}"
        )


@router.post("/install_requirements")
async def install_requirements(
    requirements: List[str],
    request: Request,
    current_user: User = Depends(get_current_user),
    script_path: str = ""
):
    """Install Python packages in a virtual environment"""
    user_dir = get_user_dir(current_user.username)
    full_script_path = os.path.join(user_dir, script_path)
    
    if not await is_safe_path(full_script_path, user_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this path"
        )
    
    if not os.path.exists(full_script_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Script not found"
        )
    
    # Get script directory
    script_dir = os.path.dirname(full_script_path)
    venv_path = os.path.join(script_dir, '.venv')
    
    if not os.path.exists(venv_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Virtual environment not found. Please create it first."
        )
    
    # Create a requirements.txt file
    req_file = os.path.join(script_dir, 'requirements.txt')
    async with aiofiles.open(req_file, 'w') as f:
        await f.write('\n'.join(requirements))
    
    # Get the pip executable from the venv
    if os.name == 'nt':  # Windows
        pip_path = os.path.join(venv_path, 'Scripts', 'pip.exe')
    else:  # Linux/Mac
        pip_path = os.path.join(venv_path, 'bin', 'pip')
    
    if not os.path.exists(pip_path):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="pip not found in the virtual environment"
        )
    
    try:
        # Install requirements
        process = await asyncio.create_subprocess_exec(
            pip_path, 'install', '-r', req_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to install requirements: {stderr.decode()}"
            )
        
        await log_activity(
            current_user.username,
            "install_requirements",
            request.client.host,
            f"Installed requirements for: {script_path}"
        )
        
        return {
            "message": "Requirements installed successfully",
            "script_path": script_path,
            "requirements": requirements,
            "output": stdout.decode()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to install requirements: {str(e)}"
        )


@router.post("/run_script")
async def run_script(
    script_path: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    args: List[str] = None,
    timeout: int = 30
):
    """Run a Python script"""
    if args is None:
        args = []
    
    user_dir = get_user_dir(current_user.username)
    full_script_path = os.path.join(user_dir, script_path)
    
    if not await is_safe_path(full_script_path, user_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this path"
        )
    
    if not os.path.exists(full_script_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Script not found"
        )
    
    # Get script directory
    script_dir = os.path.dirname(full_script_path)
    venv_path = os.path.join(script_dir, '.venv')
    
    # Check if venv exists
    if os.path.exists(venv_path):
        # Use the venv's Python
        if os.name == 'nt':  # Windows
            python_path = os.path.join(venv_path, 'Scripts', 'python.exe')
        else:  # Linux/Mac
            python_path = os.path.join(venv_path, 'bin', 'python')
    else:
        # Use system Python
        python_path = sys.executable
    
    try:
        # Create a temporary file for output
        with tempfile.NamedTemporaryFile(delete=False, mode='w+b') as tmp:
            tmp_path = tmp.name
        
        # Run the script with timeout
        process = await asyncio.create_subprocess_exec(
            python_path, full_script_path, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=script_dir
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        except asyncio.TimeoutError:
            process.kill()
            raise HTTPException(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                detail=f"Script execution timed out after {timeout} seconds"
            )
        
        await log_activity(
            current_user.username,
            "run_script",
            request.client.host,
            f"Ran script: {script_path} with args: {' '.join(args)}"
        )
        
        return {
            "message": "Script executed successfully" if process.returncode == 0 else "Script execution failed",
            "returncode": process.returncode,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
            "script_path": script_path
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run script: {str(e)}"
        )
    finally:
        # Clean up temp file
        if 'tmp_path' in locals():
            try:
                os.unlink(tmp_path)
            except:
                pass


@router.post("/schedule_script")
async def schedule_script(
    name: str,
    cron_expression: str,
    environment_vars: Dict[str, str] = None,
    request: Request = None,
    current_user: User = Depends(get_current_user),
    script_path: str = ""
):
    """Schedule a Python script to run using cron"""
    if environment_vars is None:
        environment_vars = {}
    
    user_dir = get_user_dir(current_user.username)
    full_script_path = os.path.join(user_dir, script_path)
    
    if not await is_safe_path(full_script_path, user_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this path"
        )
    
    if not os.path.exists(full_script_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Script not found"
        )
    
    # Validate cron expression (simple validation, could be improved)
    cron_parts = cron_expression.split()
    if len(cron_parts) != 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cron expression. Must have 5 parts: minute, hour, day of month, month, day of week"
        )
    
    # Scheduling logic depends on the OS
    # For Linux, we'll use the crontab
    # For other OS, we'll return an error
    if os.name != 'posix':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Script scheduling is only supported on Linux systems"
        )
    
    # Get script directory
    script_dir = os.path.dirname(full_script_path)
    venv_path = os.path.join(script_dir, '.venv')
    
    # Check if venv exists
    if os.path.exists(venv_path):
        # Use the venv's Python
        python_path = os.path.join(venv_path, 'bin', 'python')
    else:
        # Use system Python
        python_path = sys.executable
    
    # Create a wrapper script to set environment variables
    wrapper_name = f"{os.path.splitext(os.path.basename(full_script_path))[0]}_wrapper.sh"
    wrapper_path = os.path.join(script_dir, wrapper_name)
    
    wrapper_content = "#!/bin/bash\n\n"
    for var, value in environment_vars.items():
        wrapper_content += f"export {var}=\"{value}\"\n"
    
    if os.path.exists(venv_path):
        wrapper_content += f"source {os.path.join(venv_path, 'bin', 'activate')}\n"
    
    wrapper_content += f"\n{python_path} {full_script_path} > {os.path.join(script_dir, 'cron_output.log')} 2>&1\n"
    
    async with aiofiles.open(wrapper_path, 'w') as f:
        await f.write(wrapper_content)
    
    # Make the wrapper executable
    os.chmod(wrapper_path, 0o755)
    
    # Get current crontab
    try:
        process = await asyncio.create_subprocess_exec(
            'crontab', '-l',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, _ = await process.communicate()
        current_crontab = stdout.decode()
        
        # If the command failed (no crontab yet), start with an empty one
        if process.returncode != 0:
            current_crontab = ""
    except:
        current_crontab = ""
    
    # Build the cron entry
    cron_entry = f"{cron_expression} {wrapper_path} # {name} - managed by control-panel\n"
    
    # Remove any existing entry with the same name
    crontab_lines = current_crontab.splitlines()
    new_crontab_lines = [line for line in crontab_lines if f"# {name} - managed by control-panel" not in line]
    new_crontab_lines.append(cron_entry)
    new_crontab = "\n".join(new_crontab_lines)
    
    # Write to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, mode='w+') as tmp:
        tmp.write(new_crontab)
        tmp_path = tmp.name
    
    try:
        # Install the new crontab
        process = await asyncio.create_subprocess_exec(
            'crontab', tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        _, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to install crontab: {stderr.decode()}"
            )
        
        await log_activity(
            current_user.username,
            "schedule_script",
            request.client.host,
            f"Scheduled script: {script_path} with cron: {cron_expression}"
        )
        
        return {
            "message": "Script scheduled successfully",
            "name": name,
            "script_path": script_path,
            "cron_expression": cron_expression,
            "wrapper_path": wrapper_path.replace(user_dir, '').replace("\\", "/").lstrip('/')
        }
        
    except Exception as e:
        if not isinstance(e, HTTPException):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to schedule script: {str(e)}"
            )
        raise e
    finally:
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except:
            pass


@router.get("/list_scheduled")
async def list_scheduled_scripts(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """List all scheduled scripts for the user"""
    # This only works on Linux systems with crontab
    if os.name != 'posix':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Script scheduling is only supported on Linux systems"
        )
    
    try:
        # Get current crontab
        process = await asyncio.create_subprocess_exec(
            'crontab', '-l',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, _ = await process.communicate()
        current_crontab = stdout.decode()
        
        # If the command failed (no crontab yet), return empty list
        if process.returncode != 0:
            return {"scheduled_scripts": []}
        
        # Extract scheduled scripts
        scheduled_scripts = []
        for line in current_crontab.splitlines():
            # Find lines with our marker
            match = re.search(r'# (.*) - managed by control-panel', line)
            if match:
                name = match.group(1)
                
                # Extract the cron expression (first 5 parts)
                cron_parts = line.split()[:5]
                cron_expression = " ".join(cron_parts)
                
                # Extract the script path
                script_path_match = re.search(r'python (.*\.py)', line)
                if script_path_match:
                    script_path = script_path_match.group(1)
                else:
                    script_path = "Unknown"
                
                scheduled_scripts.append({
                    "name": name,
                    "cron_expression": cron_expression,
                    "script_path": script_path
                })
        
        await log_activity(
            current_user.username,
            "list_scheduled_scripts",
            request.client.host,
            "Listed scheduled scripts"
        )
        
        return {"scheduled_scripts": scheduled_scripts}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list scheduled scripts: {str(e)}"
        )


@router.delete("/unschedule_script")
async def unschedule_script(
    name: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Unschedule a previously scheduled script"""
    # This only works on Linux systems with crontab
    if os.name != 'posix':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Script scheduling is only supported on Linux systems"
        )
    
    try:
        # Get current crontab
        process = await asyncio.create_subprocess_exec(
            'crontab', '-l',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, _ = await process.communicate()
        current_crontab = stdout.decode()
        
        # If the command failed (no crontab yet), return error
        if process.returncode != 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No crontab found"
            )
        
        # Remove the entry with the given name
        crontab_lines = current_crontab.splitlines()
        found = False
        new_crontab_lines = []
        
        for line in crontab_lines:
            if f"# {name} - managed by control-panel" in line:
                found = True
                # Skip this line
            else:
                new_crontab_lines.append(line)
        
        if not found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No scheduled script with name '{name}' found"
            )
        
        new_crontab = "\n".join(new_crontab_lines)
        
        # Write to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, mode='w+') as tmp:
            tmp.write(new_crontab)
            tmp_path = tmp.name
        
        # Install the new crontab
        process = await asyncio.create_subprocess_exec(
            'crontab', tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        _, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to install crontab: {stderr.decode()}"
            )
        
        await log_activity(
            current_user.username,
            "unschedule_script",
            request.client.host,
            f"Unscheduled script: {name}"
        )
        
        return {
            "message": "Script unscheduled successfully",
            "name": name
        }
        
    except Exception as e:
        if not isinstance(e, HTTPException):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to unschedule script: {str(e)}"
            )
        raise e
    finally:
        # Clean up temp file
        if 'tmp_path' in locals():
            try:
                os.unlink(tmp_path)
            except:
                pass 