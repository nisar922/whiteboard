import redis.asyncio as aioredis
from fastapi import HTTPException, Request
from app.config import settings

redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

async def allow(key:str, limit:int , window:int) -> bool:
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key,window)
    return count <= limit

def limiter(name:str, limit:str, window:int):
    async def dependency(request: Request):
        ip = request.client.host if request.client else "unknown"
        if not await allow(f"rl:{name}:{ip}", limit, window):
            raise HTTPException(429,"Too many requests, slow down")
    return dependency