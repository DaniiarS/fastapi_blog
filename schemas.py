from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, EmailStr

# ========================================
# User Schemas
# ========================================

class UserBase(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    email: EmailStr = Field(max_length=120)

class UserCreate(UserBase):
    pass

class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=50)
    email: EmailStr | None = Field(default=None, max_length=120)
    image_file: str | None = Field(default=None, min_length=1, max_length=200)

class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    image_file: str | None
    image_path: str 


# ========================================
# Post Schemas
# ========================================

class PostBase(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=1000)

class PostCreate(PostBase):
    user_id: int # TEMPORARY

class PostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    content: str | None = Field(default=None, min_length=1, max_length=1000)

class PostResponse(PostBase):
    # First thing Pydantic tries to do when accepts SQL Alchemy ORM object is it tries reading it as dictionary:
    # Example: user["id"], post["content"]. But SQL Alchemy ORM object are accessed via attributes as user.id or post.content.
    # model_config = ConfigDict(from_attributes=True) allows Pydantic to access ORM objects fields not only as dictionary, but via attributes as well: user["id"] and uesr.id
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    date_posted: datetime
    author: UserResponse