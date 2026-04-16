from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from app.core.config import SECRET_KEY

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(hours=1)  # token expiry

    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")