from typing import Annotated

from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Example: if a user passes str into a route parameter instead of int: /posts/hello
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


# Database and SQLAlchemy imports
from sqlalchemy import select
from sqlalchemy.orm import Session
import models
from database import engine, get_db, Base

# This is executed on start. Creates tables if they don't exist in the data base, otherwise does nothing
# It safe to run it multiple times
Base.metadata.create_all(bind=engine)

# Pydantic models
from schemas import PostCreate, PostResponse, UserCreate, UserResponse

# Change the decorator on home by giving each decorator a name (ex. "home", "posts") so that it does correct routing

app = FastAPI()

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
def home_page(request: Request, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Post))
    posts = result.scalars().all()

    return templates.TemplateResponse(request, "home.html", {"posts": posts, "title": "Home"})

@app.get("/posts/{post_id}", include_in_schema=False)
def post_page(request: Request, post_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    return templates.TemplateResponse(request, "post.html", {"post": post, "title": post.title[:50]})

@app.get("/users/{user_id}/posts", include_in_schema=False, name="user_posts")
def user_posts_page(request: Request, user_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    result = db.execute(select(models.Post).where(models.Post.user_id == user.id))
    posts = result.scalars().all()

    return templates.TemplateResponse(request, "user_posts.html", {"posts": posts, "user": user, "title": f"{user.username}'s Posts"})

# ========================================================================
# API Routes: Post and User
# ========================================================================

@app.post("/api/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.User).where(models.User.username == user.username))
    existing_user = result.scalars().first()

    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exist")
    
    result = db.execute(select(models.User).where(models.User.email == user.email))
    existing_email = result.scalars().first()

    if existing_email:
        raise HTTPException(status=status.HTTP_400_BAD_REQUEST, detail="Email already exists")
    
    new_user = models.User(username=user.username, email=user.email)

    # Note: ask chatGPT about these commands
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user

@app.get("/api/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return user

@app.get("/api/users/{user_id}/posts", response_model=list[PostResponse])
def get_user_posts(user_id: int, db: Annotated[Session, Depends(get_db)]):
    # Verify if the user exists first. Otherwise the result of "None" after executing the select command on Post table and 
    # receiving an empty list as a result means two things: either a use doesn't have posts or user doesn't exist
    result = db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    result = db.execute(select(models.Post).where(models.Post.user_id == user.id))
    posts = result.scalars().all()

    return posts

@app.get("/api/users", response_model=list[UserResponse])
def get_users(db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.User))
    users = result.scalars().all()

    return users

@app.get('/api/posts', response_model=list[PostResponse])
def get_posts(db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Post))
    posts = result.scalars().all()

    return posts

@app.get('/api/posts/{post_id}', response_model=PostResponse)
def get_post(post_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    return post

@app.post('/api/posts', response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(post: PostCreate, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.User).where(models.User.id == post.user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User doesn't exist")
    
    new_post = models.Post(title=post.title, content=post.content, user_id=post.user_id)

    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    return new_post

# ========================================================================
# Exception Handler
# ========================================================================

# Exception handler: posts/"not existing id" or posts/"not existing route" for example
# Handles both "api" and "template" exceptions
@app.exception_handler(StarletteHTTPException)
def general_http_exception_handler(request: Request, exception: StarletteHTTPException):
    message = exception.detail if exception.detail else "An error occured. Please check your request and try again."

    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=exception.status_code, content={"detail": message})
    
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status_code": exception.status_code, "title": exception.status_code, "message": message},
        status_code=exception.status_code
        )

# Validation error: /posts/{str} instead of /posts/{int} for example
# Validates both for "api" and "template" returning routes
@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exception: RequestValidationError):
    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": exception.errors()})
    
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status_code": status.HTTP_422_UNPROCESSABLE_CONTENT, "title": status.HTTP_422_UNPROCESSABLE_CONTENT, "message": "Invalid request. Please check your input and try again."},
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT # this status_code parameter is used for the server not accept the request as success 200, but implicitly indicate the error happening
    )