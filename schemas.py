from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, EmailStr

# ========================================
# User Schemas
# ========================================

class UserBase(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    email: EmailStr = Field(max_length=120)

class UserCreate(UserBase):
    password: str = Field(min_length=8)

class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=50)
    email: EmailStr | None = Field(default=None, max_length=120)

class UserPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    image_file: str | None
    image_path: str

class UserPrivateResponse(UserPublicResponse):
    email: EmailStr


# ========================================
# Token Schemas
# ========================================

class Token(BaseModel):
    access_token: str
    token_type: str

# ========================================
# Post Schemas
# ========================================

class PostBase(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=1000)

class PostCreate(PostBase):
    pass

class PostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    content: str | None = Field(default=None, min_length=1, max_length=1000)

class PostResponse(PostBase):
    # First thing Pydantic tries to do when accepts SQL Alchemy ORM object is it tries reading it as dictionary:
    # Example: user["id"], post["content"]. But SQL Alchemy ORM objects are accessed via attributes as user.id or post.content.
    # model_config = ConfigDict(from_attributes=True) allows Pydantic to access ORM objects fields not only as dictionary, but via attributes as well: user["id"] and uesr.id
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    date_posted: datetime
    author: UserPublicResponse

class PaginatedPostResponse(BaseModel):
    posts: list[PostResponse]
    total: int
    skip: int
    limit: int
    has_more: bool