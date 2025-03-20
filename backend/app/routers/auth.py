from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import os
import pyotp
from dotenv import load_dotenv
from passlib.context import CryptContext
from app.models import User, Token, TokenData, UserRole
from app.database import init_db
from app.services.logging import log_activity

# Load environment variables
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "insecuresecretkeypleasechangeme")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


async def get_user(username: str):
    await init_db()
    return await User.find_one({"username": username})


async def authenticate_user(username: str, password: str):
    user = await get_user(username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username, role=role)
    except JWTError:
        raise credentials_exception
    user = await get_user(username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def get_admin_user(current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


@router.post("/token", response_model=Token)
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends()
):
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if 2FA is enabled
    if user.two_factor_enabled:
        if "totp_code" not in form_data.scopes:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Two-factor authentication code required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        totp = pyotp.TOTP(user.two_factor_secret)
        if not totp.verify(form_data.scopes[0]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid two-factor authentication code",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    # Check IP whitelist if configured
    if user.allowed_ips and len(user.allowed_ips) > 0:
        client_ip = request.client.host
        if client_ip not in user.allowed_ips:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied from this IP address",
            )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires,
    )
    
    # Update last login time
    user.last_login = datetime.utcnow()
    await user.save()
    
    # Log the activity
    await log_activity(user.username, "login", request.client.host)
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    return {
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "two_factor_enabled": current_user.two_factor_enabled
    }


@router.post("/2fa/enable")
async def enable_two_factor(current_user: User = Depends(get_current_user)):
    if current_user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication already enabled"
        )
    
    # Generate a new secret key
    secret = pyotp.random_base32()
    current_user.two_factor_secret = secret
    await current_user.save()
    
    # Generate provisioning URI for QR code
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=current_user.email,
        issuer_name="Ubuntu Control Panel"
    )
    
    return {
        "secret": secret,
        "uri": provisioning_uri
    }


@router.post("/2fa/verify")
async def verify_two_factor(
    code: str,
    current_user: User = Depends(get_current_user)
):
    if not current_user.two_factor_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication not set up"
        )
    
    totp = pyotp.TOTP(current_user.two_factor_secret)
    if not totp.verify(code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code"
        )
    
    current_user.two_factor_enabled = True
    await current_user.save()
    
    return {"message": "Two-factor authentication enabled successfully"} 