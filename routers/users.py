from typing import Annotated
from datetime import timedelta

# FastAPI imports
from fastapi import APIRouter, Depends, status, UploadFile
from fastapi.exceptions import HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from PIL import UnidentifiedImageError
from image_utils import process_file_image, delete_profile_image

from starlette.concurrency import run_in_threadpool

# auth imports
from auth import (
    create_access_token, 
    verify_password, 
    hash_password,
    CurrentUser
)

from config import settings

# Database, SQLAlchemy imports
from database import get_db
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
import models

# Pydantic Schemas imports
from schemas import UserPublicResponse, PostResponse, UserUpdate, UserCreate, UserPrivateResponse, Token


router = APIRouter()
# the path in the "router" is relative. Instead of "/api/users/" we will use an empty path ("")
# We will specify the relative part of "/api/users/" in the prefix paramter of the router

#------------------------------------------- USER -------------------------------------------
#--------------------------------------------------------------------------------------------

@router.post("", response_model=UserPrivateResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.User).where(func.lower(models.User.username) == user.username.lower()))
    existing_user = result.scalars().first()

    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exist")
    
    result = await db.execute(select(models.User).where(func.lower(models.User.email) == user.email))
    existing_email = result.scalars().first()

    if existing_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")
    
    new_user = models.User(
        username=user.username, 
        email=user.email.lower(),
        password_hash=hash_password(user.password)
    )

    # Note: ask chatGPT about these commands
    # db.add() just adds the object to the session's pending list in the memory, and no db operation happens at this point
    db.add(new_user)
    # the actual db operations take place on db.commit() and db.refresh()
    await db.commit()
    await db.refresh(new_user)

    return new_user

@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], 
                                 db: Annotated[AsyncSession, Depends(get_db)]):
    # Look up user by email (case-insensitive)
    # Note: OAuth2PasswordRequestForm uses "username" field, but we treat it as email
    result = await db.execute(select(models.User).where(func.lower(models.User.email) == form_data.username.lower()))
    user: models.User | None = result.scalars().first()

    # Verify user exists and password is correct
    # Don't reveal which one failed (security best practice)
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Incorrect email or password",
                            headers={"WWW-Authenticate": "Bearer"})
    
    # Create access token with user id as subject
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires
    )

    return Token(access_token=access_token, token_type="bearer")

@router.get("/me", response_model=UserPrivateResponse)
async def get_current_user(current_user: CurrentUser):
    """Get the currently authenticated user"""
    return current_user

@router.get("", response_model=list[UserPublicResponse])
async def get_users(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.User))
    users = result.scalars().all()

    return users

@router.get("/{user_id}", response_model=UserPublicResponse)
async def get_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return user

@router.get("/{user_id}/posts", response_model=list[PostResponse])
async def get_user_posts(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    # Verify if the user exists first. Otherwise the result of "None" after executing the select command on Post table and 
    # receiving an empty list as a result means two things: either a use doesn't have posts or user doesn't exist
    result = await db.execute(select(models.User).where(models.User.id == user_id).order_by(models.Post.date_posted.desc()))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    result = await db.execute(select(models.Post).options(selectinload(models.Post.author)).where(models.Post.user_id == user.id))
    posts = result.scalars().all()

    return posts


# PATCH method - updates information partially (some fields)
# PUT method - updates information fully (replaces old item with new)
@router.patch("/{user_id}", response_model=UserPrivateResponse)
async def update_user_partial(user_id: int, user_update: UserUpdate, 
                              current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update the user"
        )

    # check if the user to be updated exists
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # if the user exists, check if the value to be updated is not the same as it already is
    if user_update.username is not None and user_update.username.lower() != user.username.lower():
        # check if the new_username is not taken already
        result = await db.execute(select(models.User).where(func.lower(models.User.username) == user_update.username.lower()))
        existing_user = result.scalars().first()

        if existing_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")
        
    # Repeat for the email field
    if user_update.email is not None and user.email.lower() != user_update.email.lower():
        result = await db.execute(select(models.User).where(func.lower(models.User.email) == user_update.email.lower()))
        existing_user = result.scalars().first()

        if existing_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    
    if user_update.username is not None:
        user.username = user_update.username
    if user_update.email is not None:
        user.email = user_update.email.lower()
    
    await db.commit()
    await db.refresh(user)

    return user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete the user"
        )
    
    # check if the user to delete exists in the database
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User doesn't exist")
    
    old_image_filename = current_user.image_file

    # In contrast with "db.add()" db.delete() DOES need await for an async db operation to take place
    await db.delete(user)
    await db.commit()

    if old_image_filename:
        delete_profile_image(old_image_filename)

@router.patch("/{user_id}/picture", response_model=UserPrivateResponse)
async def upload_profile_picture(
                                    user_id: int, 
                                    file: UploadFile, 
                                    current_user: CurrentUser, 
                                    db: Annotated[AsyncSession, Depends(get_db)]):
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this user's picture"
        )
    
    content = await file.read()

    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"FIle too large. Maximum size is {settings.max_upload_size_bytes // (1024 * 1024)} MB."
        )

    try: 
        new_filename = await run_in_threadpool(process_file_image, content)
    except UnidentifiedImageError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Please upload a valid image (JPEG, PNG, GIF, WebP)."
        ) from err
    
    old_filename = current_user.image_file
    current_user.image_file = new_filename

    await db.commit()
    await db.refresh(current_user)

    if old_filename:
        delete_profile_image(old_filename)
    
    return current_user

@router.delete("/{user_id}/picture", response_model=UserPrivateResponse)
async def delete_profile_picture(user_id: int, current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this user's picture"
        )

    old_filename = current_user.image_file

    if old_filename is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No profile picture to delete"
        )
    
    current_user.image_file = None
    await db.commit()
    await db.refresh(current_user)

    delete_profile_image(old_filename)

    return current_user