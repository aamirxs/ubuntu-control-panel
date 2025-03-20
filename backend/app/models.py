from beanie import Document
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"


class User(Document):
    username: str
    email: EmailStr
    hashed_password: str
    role: UserRole = UserRole.USER
    is_active: bool = True
    two_factor_enabled: bool = False
    two_factor_secret: Optional[str] = None
    allowed_ips: List[str] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None

    class Settings:
        name = "users"
        

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[UserRole] = None


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.USER


class UserResponse(BaseModel):
    username: str
    email: EmailStr
    role: UserRole
    is_active: bool
    two_factor_enabled: bool
    allowed_ips: List[str]
    created_at: datetime
    last_login: Optional[datetime]


class SystemMetrics(BaseModel):
    cpu_percent: float
    memory_percent: float
    disk_usage: Dict[str, Any]
    network_io: Dict[str, Any]
    processes: List[Dict[str, Any]]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PythonJob(Document):
    name: str
    script_path: str
    owner: str
    is_scheduled: bool = False
    cron_expression: Optional[str] = None
    environment: Dict[str, str] = {}
    requirements: List[str] = []
    last_run: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "python_jobs"


class ActivityLog(Document):
    user: str
    action: str
    details: Optional[str] = None
    ip_address: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "activity_logs" 