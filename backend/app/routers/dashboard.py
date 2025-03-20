from fastapi import APIRouter, Depends, HTTPException, status, Request, WebSocket, WebSocketDisconnect
import os
import psutil
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any

from app.models import User, SystemMetrics
from app.routers.auth import get_current_user, get_admin_user
from app.services.logging import log_activity

router = APIRouter()

# Store connected clients for real-time updates
connected_clients: List[WebSocket] = []


def get_system_metrics() -> Dict[str, Any]:
    """Get system metrics (CPU, memory, disk, network)"""
    # CPU usage
    cpu_percent = psutil.cpu_percent(interval=0.5)
    cpu_times = psutil.cpu_times_percent(interval=0.5)
    cpu_count = psutil.cpu_count()
    cpu_stats = psutil.cpu_stats()
    
    # Memory usage
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    
    # Disk usage
    disks = []
    for partition in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            disks.append({
                "device": partition.device,
                "mountpoint": partition.mountpoint,
                "fstype": partition.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent
            })
        except PermissionError:
            # Skip partitions we don't have access to
            continue
    
    # Network I/O
    net_io = psutil.net_io_counters()
    net_connections = len(psutil.net_connections())
    
    # Process information
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'username', 'memory_percent', 'cpu_percent']):
        try:
            pinfo = proc.info
            processes.append({
                "pid": pinfo['pid'],
                "name": pinfo['name'],
                "username": pinfo['username'],
                "memory_percent": pinfo['memory_percent'],
                "cpu_percent": pinfo['cpu_percent']
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    # Sort processes by memory usage (descending)
    processes.sort(key=lambda x: x.get('memory_percent', 0), reverse=True)
    
    # Only return top 10 processes
    top_processes = processes[:10]
    
    metrics = {
        "timestamp": datetime.utcnow().isoformat(),
        "cpu": {
            "percent": cpu_percent,
            "times_percent": {
                "user": cpu_times.user,
                "system": cpu_times.system,
                "idle": cpu_times.idle
            },
            "count": cpu_count,
            "stats": {
                "ctx_switches": cpu_stats.ctx_switches,
                "interrupts": cpu_stats.interrupts,
                "soft_interrupts": cpu_stats.soft_interrupts,
                "syscalls": cpu_stats.syscalls
            }
        },
        "memory": {
            "total": memory.total,
            "available": memory.available,
            "used": memory.used,
            "percent": memory.percent,
            "swap": {
                "total": swap.total,
                "used": swap.used,
                "free": swap.free,
                "percent": swap.percent
            }
        },
        "disk": {
            "partitions": disks
        },
        "network": {
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv,
            "packets_sent": net_io.packets_sent,
            "packets_recv": net_io.packets_recv,
            "connections": net_connections
        },
        "processes": top_processes
    }
    
    return metrics


@router.get("/metrics")
async def get_metrics(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Get current system metrics"""
    metrics = get_system_metrics()
    
    await log_activity(
        current_user.username,
        "get_metrics",
        request.client.host,
        "Retrieved system metrics"
    )
    
    return metrics


@router.websocket("/ws")
async def metrics_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time system metrics"""
    await websocket.accept()
    
    # Authentication for WebSocket
    try:
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=1008, reason="Missing authentication token")
            return
        
        # Validate token and get user
        from app.routers.auth import jwt, SECRET_KEY, ALGORITHM, get_user
        
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            if not username:
                await websocket.close(code=1008, reason="Invalid authentication")
                return
            
            user = await get_user(username)
            if not user:
                await websocket.close(code=1008, reason="User not found")
                return
        except Exception:
            await websocket.close(code=1008, reason="Invalid authentication")
            return
        
        # Add to connected clients
        connected_clients.append(websocket)
        
        # Log connection
        client_ip = websocket.client.host
        await log_activity(username, "metrics_connect", client_ip, "Connected to real-time metrics")
        
        try:
            # Keep connection alive
            while True:
                # Get metrics every 2 seconds
                metrics = get_system_metrics()
                await websocket.send_json(metrics)
                await asyncio.sleep(2)
        except WebSocketDisconnect:
            # Handle client disconnect
            if websocket in connected_clients:
                connected_clients.remove(websocket)
            await log_activity(username, "metrics_disconnect", client_ip, "Disconnected from real-time metrics")
        except Exception as e:
            print(f"WebSocket error: {e}")
            if websocket in connected_clients:
                connected_clients.remove(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")


@router.get("/stats")
async def get_system_stats(
    request: Request,
    current_user: User = Depends(get_admin_user)
):
    """Get detailed system statistics (admin only)"""
    # CPU stats
    cpu_freq = psutil.cpu_freq()
    load_avg = psutil.getloadavg()
    
    # Memory stats
    memory = psutil.virtual_memory()
    
    # Disk I/O
    disk_io = psutil.disk_io_counters()
    
    # Network addresses
    net_addresses = []
    for nic, addrs in psutil.net_if_addrs().items():
        nic_info = {"name": nic, "addresses": []}
        for addr in addrs:
            addr_info = {
                "family": str(addr.family),
                "address": addr.address,
                "netmask": addr.netmask,
                "broadcast": addr.broadcast
            }
            nic_info["addresses"].append(addr_info)
        net_addresses.append(nic_info)
    
    # Network stats
    net_stats = []
    for nic, stats in psutil.net_if_stats().items():
        nic_stats = {
            "name": nic,
            "isup": stats.isup,
            "duplex": stats.duplex,
            "speed": stats.speed,
            "mtu": stats.mtu
        }
        net_stats.append(nic_stats)
    
    # OS information
    users = []
    for user in psutil.users():
        user_info = {
            "name": user.name,
            "terminal": user.terminal,
            "host": user.host,
            "started": datetime.fromtimestamp(user.started).isoformat()
        }
        users.append(user_info)
    
    boot_time = datetime.fromtimestamp(psutil.boot_time()).isoformat()
    
    stats = {
        "cpu": {
            "freq": {
                "current": cpu_freq.current if cpu_freq else None,
                "min": cpu_freq.min if cpu_freq else None,
                "max": cpu_freq.max if cpu_freq else None
            },
            "load_avg": {
                "1min": load_avg[0],
                "5min": load_avg[1],
                "15min": load_avg[2]
            }
        },
        "memory": {
            "total": memory.total,
            "available": memory.available,
            "used": memory.used,
            "free": memory.free,
            "percent": memory.percent,
            "buffers": memory.buffers,
            "cached": memory.cached
        },
        "disk_io": {
            "read_count": disk_io.read_count if disk_io else None,
            "write_count": disk_io.write_count if disk_io else None,
            "read_bytes": disk_io.read_bytes if disk_io else None,
            "write_bytes": disk_io.write_bytes if disk_io else None,
            "read_time": disk_io.read_time if disk_io else None,
            "write_time": disk_io.write_time if disk_io else None
        },
        "network": {
            "interfaces": net_addresses,
            "stats": net_stats
        },
        "system": {
            "boot_time": boot_time,
            "users": users
        }
    }
    
    await log_activity(
        current_user.username,
        "get_system_stats",
        request.client.host,
        "Retrieved detailed system statistics"
    )
    
    return stats


@router.get("/users")
async def get_logged_in_users(
    request: Request,
    current_user: User = Depends(get_admin_user)
):
    """Get list of logged in users (admin only)"""
    users = []
    for user in psutil.users():
        user_info = {
            "name": user.name,
            "terminal": user.terminal,
            "host": user.host,
            "started": datetime.fromtimestamp(user.started).isoformat()
        }
        users.append(user_info)
    
    await log_activity(
        current_user.username,
        "get_logged_in_users",
        request.client.host,
        "Retrieved list of logged in users"
    )
    
    return {"users": users} 