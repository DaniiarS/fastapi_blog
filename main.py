from fastapi import FastAPI, Request, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Example: if a user passes str into a route parameter instead of int: /posts/hello
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Change the decorator on home by giving each decorator a name (ex. "home", "posts") so that it does correct routing

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

posts: list[dict] = [
    {
        "id": 1,
        "title": "FastAPI Project post",
        "content": "FastAPI is the Python framework that helps to build web-applications.",
        "author": "Daniiar Suiunbekov",
        "date": "February, 2026"
    },
    {
        "id": 2,
        "title": "Hello World Project",
        "content": "Hello-world-project is the simplest form of a project to practice concepts learned. Mostly the term is used in programming when one creates a simple program.",
        "author": "Anton Makarov",
        "date": "January, 2026"
    }
]

# ==================================
# Template Routes
# ==================================

@app.get('/', include_in_schema=False, name="home")
@app.get('/posts', include_in_schema=False, name="posts")
def home_page(request: Request):
    return templates.TemplateResponse(request, "home.html", {"posts": posts, "title": "Home"})

@app.get("/posts/{post_id}", include_in_schema=False, name ="post")
def post_page(request: Request, post_id: int):
    for post in posts:
        
        if post.get("id") == post_id:
            title = post["title"][:50]
            return templates.TemplateResponse(request, "post.html", {"post": post, "title": title})

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

# ==================================
# API Routes
# ==================================

@app.get('/api/posts')
def get_posts():
    return posts

@app.get('/api/posts/{post_id}')
def get_post(post_id: int):
    for post in posts:
        if post.get("id") == post_id:
            return post
    
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

# ==================================
# Exception Handler
# ==================================

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
def validation_exception_hamdler(request: Request, exception: RequestValidationError):
    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": exception.errors()})
    
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status_code": status.HTTP_422_UNPROCESSABLE_CONTENT, "title": status.HTTP_422_UNPROCESSABLE_CONTENT, "message": "Invalid request. Please check your input and try again."},
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT # this status_code parameter is used for the server not accept the request as success 200, but implicitly indicate the error happening
    )