from typing import Annotated

# FastAPI imports
from fastapi import APIRouter, Depends,status
from fastapi.exceptions import HTTPException

# Database, SQLAlchemy imports
from database import get_db
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
import models

# Pydantic Schemas imports
from schemas import UserResponse, PostResponse, UserUpdate, UserCreate


router = APIRouter()
# the path in the "router" is relative. Instead of "/api/users/" we will use an empty path ("")
# We will specify the relative part of "/api/users/" in the prefix paramter of the router

#------------------------------------------- USER -------------------------------------------
#--------------------------------------------------------------------------------------------
@router.get("", response_model=list[UserResponse])
async def get_users(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.User))
    users = result.scalars().all()

    return users

@router.get("/{user_id}", response_model=UserResponse)
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

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.User).where(models.User.username == user.username))
    existing_user = result.scalars().first()

    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exist")
    
    result = await db.execute(select(models.User).where(models.User.email == user.email))
    existing_email = result.scalars().first()

    if existing_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")
    
    new_user = models.User(username=user.username, email=user.email)

    # Note: ask chatGPT about these commands
    # db.add() just adds the object to the session's pending list in the memory, and no db operation happens at this point
    db.add(new_user)
    # the actual db operations take place on db.commit() and db.refresh()
    await db.commit()
    await db.refresh(new_user)

    return new_user

# PATCH method - updates information partially (some fields)
# PUT method - updates information fully (replaces old item with new)
@router.patch("/{user_id}", response_model=UserResponse)
async def update_user_partial(user_id: int, user_update: UserUpdate, db: Annotated[AsyncSession, Depends(get_db)]):
    # check is the user to be updated exists
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # if the user exists, check if the value to be updated is not the same as it already is
    if user_update.username is not None and user_update.username != user.username:
        # check if the new_username is not taken already
        result = await db.execute(select(models.User).where(models.User.username == user_update.username))
        existing_user = result.scalars().first()

        if existing_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")
        
    # Repeat for the email field
    if user_update.email is not None and user.email != user_update.email:
        result = await db.execute(select(models.User).where(models.User.email == user_update.email))
        existing_user = result.scalars().first()

        if existing_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    
    if user_update.username is not None:
        user.username = user_update.username
    if user_update.email is not None:
        user.email = user_update.email
    if user_update.image_file is not None:
        user.image_file = user_update.image_file
    
    await db.commit()
    await db.refresh(user)

    return user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    # check if the user to delete exists in the database
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User doesn't exist")
    
    # In contrast with "db.add()" db.delete() DOES need await for an async db operation to take place
    await db.delete(user)
    await db.commit()