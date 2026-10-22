from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import engine, Base
from app import models
from app.auth import router as auth_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield    

app = FastAPI(title="Whiteboard", lifespan=lifespan)
app.include_router(auth_router)

@app.get("/health")
async def health():
    return {"status": "ok"}