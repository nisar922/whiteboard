from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import engine, Base
from app import models

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield    

app = FastAPI(title="Whiteboard", lifespan=lifespan)
@app.get("/health")
async def health():
    return {"status": "ok"}