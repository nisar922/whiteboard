import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app import models
from app.auth import router as auth_router
from app.boards import router as boards_router
from app.database import engine, Base
from app.websocket import router as ws_router, redis_listener

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    task = asyncio.create_task(redis_listener())
    yield   
    task.cancel() 

app = FastAPI(title="Whiteboard", lifespan=lifespan)

@app.get("/health")
async def health():
    return{"status":"ok"}

app.include_router(auth_router)
app.include_router(boards_router)
app.include_router(ws_router)

app.mount("/",StaticFiles(directory=Path(__file__).parent / "client", html=True), name="client")