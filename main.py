from typing import Annotated

from contextlib import asynccontextmanager

from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


# Database and SQLAlchemy imports
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import models
from database import engine, get_db, Base


# Pydantic models
from schemas import PostCreate, PostResponse, UserCreate, UserResponse, PostUpdate, UserUpdate

# This is executed on start. Creates tables if they don't exist in the database, otherwise does nothing
# It is safe to run it multiple times
# The following lines were changed to async version of creating the tables in the database
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(lifespan=lifespan)

# Mounting: these lines tell FastAPI: “Serve files from these folders directly over HTTP.” (c) ChatGPT
# When a request comes FastAPI checks if starts with "/media" or "/static", for example "/media/uploads/uid_123.png"
# It cuts the "/media" ("/uploads/uid_123.png" remains). And then it search this file inside the folder specified in
# the StaticFiles(directory="Look_to_this_folder"), and serves the file
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")


templates = Jinja2Templates(directory="templates")

# ========================================================================
# Template Routes
# ========================================================================

@app.get('/', include_in_schema=False, name="home")
@app.get('/posts', include_in_schema=False, name="posts")
async def home_page(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    # we have to use selectinload beacuse sync sqlalchemy does lazyloading, but async sqlalchemy doesn't support lazyloading
    # lazyloading enables to access the related fields of an object. For instance, if we load a Post object, on the background sqlalchemy runs sync query to load the Post.author. Therefore, after loading Post object we can access Post.author.username. But with the async sqlalchemy it doesn't work, because the query on the background is sync and it blocks the event loop
    # to handle this we have to use "selectinload" which wraps that sync query into async and loads the related fields
    result = await db.execute(select(models.Post).options(selectinload(models.Post.author)))
    posts = result.scalars().all()

    return templates.TemplateResponse(request, "home.html", {"posts": posts, "title": "Home"})

@app.get("/posts/{post_id}", include_in_schema=False)
async def post_page(request: Request, post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.Post).options(selectinload(models.Post.author)).where(models.Post.id == post_id))
    post = result.scalars().first()

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    return templates.TemplateResponse(request, "post.html", {"post": post, "title": post.title[:50]})

@app.get("/users/{user_id}/posts", include_in_schema=False, name="user_posts")
async def user_posts_page(request: Request, user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    # no need to add ".options()" in the following line, beacuse we are not referencing the related fields of the object
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    # here we have to use ".options()" because futher in the "user_posts.html" template we are referring to the post.author.username and other related fields of the Post object
    result = await db.execute(select(models.Post).options(selectinload(models.Post.author)).where(models.Post.user_id == user.id))
    posts = result.scalars().all()

    return templates.TemplateResponse(request, "user_posts.html", {"posts": posts, "user": user, "title": f"{user.username}'s Posts"})

# ========================================================================
# API Routes: Post and User
# ========================================================================


#------------------------------------------- USER -------------------------------------------
#--------------------------------------------------------------------------------------------
@app.get("/api/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return user

@app.get("/api/users/{user_id}/posts", response_model=list[PostResponse])
async def get_user_posts(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    # Verify if the user exists first. Otherwise the result of "None" after executing the select command on Post table and 
    # receiving an empty list as a result means two things: either a use doesn't have posts or user doesn't exist
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    result = await db.execute(select(models.Post).options(selectinload(models.Post.author)).where(models.Post.user_id == user.id))
    posts = result.scalars().all()

    return posts

@app.get("/api/users", response_model=list[UserResponse])
async def get_users(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.User))
    users = result.scalars().all()

    return users

@app.post("/api/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
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
@app.patch("/api/users/{user_id}", response_model=UserResponse)
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

@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    # check if the user to delete exists in the database
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User doesn't exist")
    
    # In contrast with "db.add()" db.delete() DOES need await for an async db operation to take place
    await db.delete(user)
    await db.commit()



#------------------------------------------- POST -------------------------------------------
#--------------------------------------------------------------------------------------------
@app.get('/api/posts', response_model=list[PostResponse])
async def get_posts(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.Post).options(selectinload(models.Post.author)))
    posts = result.scalars().all()

    return posts

@app.get('/api/posts/{post_id}', response_model=PostResponse)
async def get_post(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.Post).options(selectinload(models.Post.author)).where(models.Post.id == post_id))
    post = result.scalars().first()
    
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    return post

@app.put("/api/posts/{post_id}", response_model=PostResponse)
async def update_post_full(post_id: int, post_data: PostCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    # check if the post that needs to be changed exists
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    # check if the user requesting an update exists
    result = await db.execute(select(models.User).where(models.User.id == post_data.user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    post.title = post_data.title
    post.content = post_data.content
    post.user_id = post_data.user_id

    await db.commit()
    await db.refresh(post, attribute_names=["author"])

    return post

@app.patch("/api/posts/{post_id}", response_model=PostResponse)
async def update_post_partial(post_id: int, post_data: PostUpdate, db: Annotated[AsyncSession, Depends(get_db)]):
    # check if the post to be updated exists
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    # this line excludes fields in the request which have None values
    update_data = post_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(post, key, value)
    
    await db.commit()
    await db.refresh(post, attribute_names=["author"])

    return post

# DELETE Methods doesn't have response body, instead it returns HTTP 204 code, which means that
# request was successfull, and deletion took place
@app.delete("/api/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    await db.delete(post)
    await db.commit()
    

@app.post('/api/posts', response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(post: PostCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.User).where(models.User.id == post.user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User doesn't exist")
    
    new_post = models.Post(title=post.title, content=post.content, user_id=post.user_id)

    db.add(new_post)
    await db.commit()
    await db.refresh(new_post, attribute_names=["author"])

    return new_post

# ========================================================================
# Exception Handler
# ========================================================================

# Exception handler: posts/"not existing id" or posts/"not existing route" for example
# Handles both "api" and "template" exceptions
@app.exception_handler(StarletteHTTPException)
async def general_http_exception_handler(request: Request, exception: StarletteHTTPException):

    if request.url.path.startswith("/api"):
        return await http_exception_handler(request, exception)

    message = exception.detail if exception.detail else "An error occured. Please check your request and try again."
    
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status_code": exception.status_code, "title": exception.status_code, "message": message},
        status_code=exception.status_code
        )

# Validation error: /posts/{str} instead of /posts/{int} for example
# Validates both for "api" and "template" returning routes
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exception: RequestValidationError):
    if request.url.path.startswith("/api"):
        return await request_validation_exception_handler(request, exception)
    
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status_code": status.HTTP_422_UNPROCESSABLE_CONTENT, "title": status.HTTP_422_UNPROCESSABLE_CONTENT, "message": "Invalid request. Please check your input and try again."},
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT # this status_code parameter is used for the server not accept the request as success 200, but implicitly indicate the error happening
    )