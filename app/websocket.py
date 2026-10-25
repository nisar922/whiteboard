import json
import time
import uuid
from collections import defaultdict
import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from sqlalchemy import select
from app.access import has_access
from app.config import settings
from app.database import SessionLocal
from app.models import Board, BoardMember, User
router = APIRouter()
redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
SERVER_ID = uuid.uuid4().hex
MAX_USERS = 10
DRAW_EVENTS = {"point", "delete", "clear", "end"}
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
conn_info: dict[WebSocket, dict] = {}
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
async def load_roster(board_id: int) -> list[dict]:
    async with SessionLocal() as db:
        board = await db.get(Board, board_id)
        if not board:
            return []
        owner = await db.get(User, board.owner_id)
        rows = await db.execute(
            select(BoardMember, User)
            .join(User, User.id == BoardMember.user_id)
            .where(BoardMember.board_id == board_id)
            .order_by(User.email)
        )
        roster = [{"user_id": owner.id, "email": owner.email,
                   "is_owner": True, "can_edit": True}]
        for member, user in rows.all():
            roster.append({"user_id": user.id, "email": user.email,
                           "is_owner": False, "can_edit": member.can_edit})
    return roster
async def broadcast_roster(board_id: int):
    msg = {"type": "roster", "members": await load_roster(board_id)}
    await manager.broadcast(board_id, msg)
    await publish(board_id, msg)
def set_local_permission(board_id: int, user_id: int, can_edit: bool):
    for ws in manager.rooms.get(board_id, []):
        info = conn_info.get(ws)
        if info and info["user_id"] == user_id and not info["is_owner"]:
            info["can_edit"] = can_edit
async def handle_set_perm(board_id: int, info: dict, data: dict):
    if not info["is_owner"]:
        return
    target = data.get("user_id")
    if not isinstance(target, int) or target == info["user_id"]:
        return
    can_edit = bool(data.get("can_edit"))
    async with SessionLocal() as db:
        member = await db.get(BoardMember, (board_id, target))
        if not member:
            return
        member.can_edit = can_edit
        await db.commit()
    set_local_permission(board_id, target, can_edit)
    await publish(board_id, {"type": "perm", "user_id": target, "can_edit": can_edit})
    await broadcast_roster(board_id)
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
            if data.get("type") == "perm":
                set_local_permission(board_id, data["user_id"], data["can_edit"])
                continue
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
    info = None
    async with SessionLocal() as db:
        board = await db.get(Board, board_id)
        allowed = await has_access(db, board, user_id)
        user = await db.get(User, user_id)
        if allowed and user:
            is_owner = board.owner_id == user_id
            can_edit = True
            if not is_owner:
                member = await db.get(BoardMember, (board_id, user_id))
                can_edit = bool(member and member.can_edit)
            info = {"user_id": user_id, "email": user.email,
                    "is_owner": is_owner, "can_edit": can_edit}
            title, code = board.title, board.join_code
    if info is None:
        await websocket.close(code=1008)
        return
    email = info["email"]
    online = set(await redis.hvals(f"presence:{board_id}"))
    if email not in online and len(online) >= MAX_USERS:
        await websocket.accept()
        await websocket.send_json(
            {"type": "error", "message": f"Room is full (max {MAX_USERS} people)"}
        )
        await websocket.close(code=1008)
        return
    conn_id = uuid.uuid4().hex[:8]
    conn_info[websocket] = info
    await manager.connect(board_id, websocket)
    strokes = await load_state(board_id)
    await websocket.send_json({
        "type": "init",
        "strokes": strokes,
        "you": info,
        "room": {"title": title,
                 "code": code if info["is_owner"] else None,
                 "max_users": MAX_USERS},
    })
    await redis.hset(f"presence:{board_id}", conn_id, email)
    await broadcast_presence(board_id)
    await broadcast_roster(board_id)
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
            if not isinstance(data, dict):
                continue
            t = data.get("type")
            if t == "cursor":
                msg = {"type": "cursor", "u": email,
                       "x": data.get("x"), "y": data.get("y")}
                await manager.broadcast(board_id, msg, websocket)
                await publish(board_id, msg)
            elif t == "set_perm":
                await handle_set_perm(board_id, info, data)
            elif t in DRAW_EVENTS:
                if not info["can_edit"]:
                    continue
                try:
                    apply_event(strokes, data)
                except (KeyError, TypeError, AttributeError):
                    continue
                if t in ("delete", "clear", "end"):
                    await save_state(board_id)
                if t == "end":
                    continue
                await manager.broadcast(board_id, data, websocket)
                await publish(board_id, data)
    except WebSocketDisconnect:
        pass
    finally:
        conn_info.pop(websocket, None)
        manager.disconnect(board_id, websocket)
        await redis.hdel(f"presence:{board_id}", conn_id)
        await broadcast_presence(board_id)
        if board_id not in manager.rooms:
            await save_state(board_id)
            states.pop(board_id, None)