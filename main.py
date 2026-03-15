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

# Import Routers from routers
from routers import users, posts

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
# When a request comes FastAPI checks if a route starts with "/media" or "/static", for example "/media/uploads/uid_123.png"
# It cuts the "/media" ("/uploads/uid_123.png" remains). And then it search this file inside the folder specified in
# the StaticFiles(directory="Look_to_this_folder"), and serves the file
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")

# Include routers that are created in the "routers" to the "app" instance
# The foolowing lines connect the routers to the "app" instance. Prefix parameter adds the URL prefix to all routes in the router. So the router's empty string "" becomes the prefix.
# "tags" parameter is used for FastAPI's docs page
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(posts.router, prefix="/api/posts", tags=["posts"])

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
    result = await db.execute(select(models.Post).options(selectinload(models.Post.author)).order_by(models.Post.date_posted.desc()))
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
    result = await db.execute(select(models.Post).options(selectinload(models.Post.author)).where(models.Post.user_id == user.id).order_by(models.Post.date_posted.desc()))
    posts = result.scalars().all()

    return templates.TemplateResponse(request, "user_posts.html", {"posts": posts, "user": user, "title": f"{user.username}'s Posts"})

# ========================================================================
# API Routes: Post and User
# ========================================================================


#------------------------------------------- USER -------------------------------------------
#--------------------------------------------------------------------------------------------

#                                   USERS routes moved to ./routes/users.py

#--------------------------------------------------------------------------------------------
#--------------------------------------------------------------------------------------------


#------------------------------------------- POST -------------------------------------------
#--------------------------------------------------------------------------------------------

#                                   POSTS routes moved to ./routes/posts.py

#--------------------------------------------------------------------------------------------
#--------------------------------------------------------------------------------------------

@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"title": "Login"})

@app.get("/register", include_in_schema=False)
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"title": "Register"})

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