import json
import time
import uuid
from collections import defaultdict
import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from app.access import has_access
from app.config import settings
from app.database import SessionLocal
from app.models import Board, User
router = APIRouter()
redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
SERVER_ID = uuid.uuid4().hex
class ConnectionManager:
    def __init__(self):
        self.rooms: dict[int, list[WebSocket]] = defaultdict(list)
    async def connect(self, board_id: int, ws: WebSocket):
        await ws.accept()
        self.rooms[board_id].append(ws)
    def disconnect(self, board_id: int, ws: WebSocket):
        if ws in self.rooms.get(board_id, []):
            self.rooms[board_id].remove(ws)
        if board_id in self.rooms and not self.rooms[board_id]:
            del self.rooms[board_id]
    async def broadcast(self, board_id: int, message: dict, sender=None):
        for conn in list(self.rooms.get(board_id, [])):
            if conn is not sender:
                try:
                    await conn.send_json(message)
                except Exception:
                    pass
manager = ConnectionManager()
states: dict[int, dict] = {}
async def load_state(board_id: int) -> dict:
    if board_id not in states:
        async with SessionLocal() as db:
            board = await db.get(Board, board_id)
            states[board_id] = dict((board.state or {}).get("strokes", {}))
    return states[board_id]
async def save_state(board_id: int):
    async with SessionLocal() as db:
        board = await db.get(Board, board_id)
        if board:
            board.state = {"strokes": states.get(board_id, {})}
            await db.commit()
def apply_event(strokes: dict, data: dict):
    t = data.get("type")
    if t == "point":
        strokes.setdefault(data["id"], []).append(data["p"])
    elif t == "delete":
        strokes.pop(data["id"], None)
    elif t == "clear":
        strokes.clear()
async def publish(board_id: int, data: dict):
    await redis.publish(
        f"board:{board_id}", json.dumps({"sid": SERVER_ID, "data": data})
    )
async def broadcast_presence(board_id: int):
    members = await redis.hgetall(f"presence:{board_id}")
    msg = {"type": "presence", "users": sorted(set(members.values()))}
    await manager.broadcast(board_id, msg)
    await publish(board_id, msg)
async def redis_listener():
    pubsub = redis.pubsub()
    await pubsub.psubscribe("board:*")
    async for msg in pubsub.listen():
        if msg["type"] != "pmessage":
            continue
        try:
            payload = json.loads(msg["data"])
            if payload["sid"] == SERVER_ID:
                continue
            board_id = int(msg["channel"].split(":")[1])
            data = payload["data"]
            strokes = states.get(board_id)
            if strokes is not None:
                apply_event(strokes, data)
            await manager.broadcast(board_id, data)
        except Exception as e:
            print("redis listener error:", e)
@router.websocket("/ws/boards/{board_id}")
async def board_ws(websocket: WebSocket, board_id: int, token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        await websocket.close(code=1008)
        return
    async with SessionLocal() as db:
        board = await db.get(Board, board_id)
        allowed = await has_access(db, board, user_id)
        user = await db.get(User, user_id)
    if not allowed or not user:
        await websocket.close(code=1008)
        return
    email = user.email
    conn_id = uuid.uuid4().hex[:8]
    await manager.connect(board_id, websocket)
    strokes = await load_state(board_id)
    await websocket.send_json({"type": "init", "strokes": strokes})
    await redis.hset(f"presence:{board_id}", conn_id, email)
    await broadcast_presence(board_id)
    try:
        window_start = time.monotonic()
        count = 0
        while True:
            data = await websocket.receive_json()
            now = time.monotonic()
            if now - window_start >= 1:
                window_start, count = now, 0
            count += 1
            if count > 200:
                await websocket.close(code=1008)
                break
            t = data.get("type")
            if t == "cursor":
                data = {"type": "cursor", "u": email,
                        "x": data.get("x"), "y": data.get("y")}
            else:
                apply_event(strokes, data)
                if t in ("delete", "clear", "end"):
                    await save_state(board_id)
                if t == "end":
                    continue
            await manager.broadcast(board_id, data, websocket)
            await publish(board_id, data)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(board_id, websocket)
        await redis.hdel(f"presence:{board_id}", conn_id)
        await broadcast_presence(board_id)
        if board_id not in manager.rooms:
            await save_state(board_id)
            states.pop(board_id, None)