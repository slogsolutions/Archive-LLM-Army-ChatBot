# schema for Validation like joi/zod coz in-build
from pydantic import BaseModel


class UserCreate(BaseModel):
    army_number: str
    name: str
    password: str


class UserLogin(BaseModel):
    army_number: str
    password: str
