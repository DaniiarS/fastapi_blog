from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

posts: list[dict] = [
    {
        "id": 1,
        "title": "Fast API Project post",
        "author": "Daniiar Suiunbekov",
        "date": "February, 2026"
    },
    {
        "id": 2,
        "title": "Hello World Project",
        "author": "Anton Makarov",
        "date": "January, 2026"
    }
]

@app.get('/posts', response_class=HTMLResponse, include_in_schema=False)
@app.get('/', response_class=HTMLResponse, include_in_schema=False)
def home():
    return f"<h1>{posts[0]['title']}</h1>"

@app.get('/api/posts')
def get_posts():
    return posts