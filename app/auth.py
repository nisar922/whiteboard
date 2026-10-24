from datetime import datetime, timedelta, timezone
import bcrypt
from jose import jwt,  JWTError
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserOut, Token
from app.ratelimit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])

def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()

def verify_password(p: str, hashed: str) -> bool:
    return bcrypt.checkpw(p.encode(), hashed.encode())

def create_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {"sub": str(user_id), "exp": exp}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

@router.post("/register", response_model=UserOut, status_code=201)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")
    user = User(email=data.email, hashed_password=hash_password(data.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@router.post("/login", response_model=Token,dependencies=[Depends(limiter("login",10,60))])
async def login(data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")
    return {"access_token": create_token(user.id), "token_type": "bearer"}


bearer = HTTPBearer()

async def get_current_user(
        creds: HTTPAuthorizationCredentials = Depends(bearer),
        db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(creds.credentials, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except(JWTError, KeyError, ValueError):
        raise HTTPException(401, "Invalid or expired tokek")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(401, "User not found")
    return user
