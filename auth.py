from typing import Any, Annotated
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import models
from database import get_db

import jwt
from pwdlib import PasswordHash

from config import settings

password_hash = PasswordHash.recommended()

# tokenUrl has to match the login endpoint path
# OAuth2PasswordBearer extracts the token from the authorization header
# when a client sends that, the scheme extracts that token for us
# this enables the authorize button in our docs which makes testing authentication a lot easier
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/token")

def hash_password(password: str) -> str:
    return password_hash.hash(password)

# NOTE: encryption is reversable, but hashing is not
# argon2 generates a random salt for each hash, so that same password produces different hashes each time
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)

def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    
    encode_jwt: str = jwt.encode(
        payload=to_encode,
        key=settings.secret_key.get_secret_value(),
        algorithm=settings.algorithm
    )

    return encode_jwt

def verify_access_token(token: str) -> str | None:
    """Verify a JWT access token and return the subject (user id) if valid."""
    try:
        payload = jwt.decode(
            jwt=token,
            key=settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
            options={"require": ["exp", "sub"]}
        )
    except jwt.InvalidTokenError:
        return None
    else:
        return payload.get("sub")

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], 
                           db: Annotated[AsyncSession, Depends(get_db)]) -> models.User:
    user_id = verify_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"} # If a server returns 401 Unauthorized, it must include a WWW-Authenticate header telling the client what authentication method to use.
        )
    
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"} # If a server returns 401 Unauthorized, it must include a WWW-Authenticate header telling the client what authentication method to use.
        )
    
    result = await db.execute(select(models.User).where(models.User.id == user_id_int))
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"} # If a server returns 401 Unauthorized, it must include a WWW-Authenticate header telling the client what authentication method to use.
        )
    
    return user

CurrentUser = Annotated[models.User, Depends(get_current_user)]