from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List
from app.models import User, UserCreate, UserResponse, UserRole
from app.database import init_db
from app.routers.auth import get_admin_user, get_current_user, get_password_hash
from app.services.logging import log_activity

router = APIRouter()


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_create: UserCreate,
    request: Request,
    current_user: User = Depends(get_admin_user)
):
    """Create a new user (admin only)"""
    await init_db()
    
    # Check if username already exists
    existing_user = await User.find_one({"username": user_create.username})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    existing_email = await User.find_one({"email": user_create.email})
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    hashed_password = get_password_hash(user_create.password)
    new_user = User(
        username=user_create.username,
        email=user_create.email,
        hashed_password=hashed_password,
        role=user_create.role
    )
    await new_user.save()
    
    # Log activity
    await log_activity(
        current_user.username,
        "create_user",
        request.client.host,
        f"Created user: {new_user.username}"
    )
    
    return UserResponse(
        username=new_user.username,
        email=new_user.email,
        role=new_user.role,
        is_active=new_user.is_active,
        two_factor_enabled=new_user.two_factor_enabled,
        allowed_ips=new_user.allowed_ips,
        created_at=new_user.created_at,
        last_login=new_user.last_login
    )


@router.get("/", response_model=List[UserResponse])
async def list_users(current_user: User = Depends(get_admin_user)):
    """List all users (admin only)"""
    await init_db()
    users = await User.find_all().to_list()
    return [
        UserResponse(
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            two_factor_enabled=user.two_factor_enabled,
            allowed_ips=user.allowed_ips,
            created_at=user.created_at,
            last_login=user.last_login
        ) for user in users
    ]


@router.get("/{username}", response_model=UserResponse)
async def get_user_details(
    username: str,
    current_user: User = Depends(get_current_user)
):
    """Get details of a user"""
    # Only allow admins to view other users' details
    if current_user.username != username and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    await init_db()
    user = await User.find_one({"username": username})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        two_factor_enabled=user.two_factor_enabled,
        allowed_ips=user.allowed_ips,
        created_at=user.created_at,
        last_login=user.last_login
    )


@router.put("/{username}/ip-whitelist")
async def update_ip_whitelist(
    username: str,
    ip_addresses: List[str],
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Update IP whitelist for a user"""
    # Only allow admins or the user themselves to update their IP whitelist
    if current_user.username != username and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    await init_db()
    user = await User.find_one({"username": username})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.allowed_ips = ip_addresses
    await user.save()
    
    # Log activity
    await log_activity(
        current_user.username,
        "update_ip_whitelist",
        request.client.host,
        f"Updated IP whitelist for user: {username}"
    )
    
    return {"message": "IP whitelist updated successfully"}


@router.delete("/{username}")
async def delete_user(
    username: str,
    request: Request,
    current_user: User = Depends(get_admin_user)
):
    """Delete a user (admin only)"""
    # Prevent admin from deleting themselves
    if current_user.username == username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    await init_db()
    user = await User.find_one({"username": username})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    await user.delete()
    
    # Log activity
    await log_activity(
        current_user.username,
        "delete_user",
        request.client.host,
        f"Deleted user: {username}"
    )
    
    return {"message": "User deleted successfully"} 