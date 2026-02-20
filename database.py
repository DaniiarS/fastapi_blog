from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# This file is more like a configuration to the DataBase that is going to be used

SQLALCHEMY_DATABASE_URL = "sqlite:///./blog.db"

# create engine to connect to the database
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    with SessionLocal() as db:
        yield db