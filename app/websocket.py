from collections import defaultdict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from app.config import settings
from app.database import SessionLocal
from app.models import Board
from app.access import has_access

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.rooms: dict[int, list[WebSocket]] = defaultdict(list)

    async def connect(self, board_id: int, ws: WebSocket):
        await ws.accept()
        self.rooms[board_id].append(ws)

    def disconnect(self, board_id: int, ws: WebSocket):
        self.rooms[board_id].remove(ws)
        if not self.rooms[board_id]:
            del self.rooms[board_id]

    async def broadcast(self, board_id: int, message: dict, sender: WebSocket):
        for conn in list(self.rooms.get(board_id, [])):
            if conn is not sender:
                await conn.send_json(message)

manager = ConnectionManager()

states: dict[int, dict]={}

async def load_state(board_id: int) ->dict:
    if board_id not in states:
        async with SessionLocal() as db:
            board = await db.get(Board, board_id)
            states[board_id] = dict((board.state or {}).get("strokes",{}))
    return states[board_id] 

async def save_state(borad_id: int):
    async with SessionLocal() as db:
        borad = await db.get(Board, borad_id)
        if borad:
            borad.state = {"strokes": states.get(borad_id, {})}
            await db.commit() 

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
        allowed = await db.get(Board, board_id)
    if not allowed:
        await websocket.close(code=1008)
        return
    await manager.connect(board_id, websocket)
    strokes = await load_state(board_id)
    await websocket.send_json({"type": "init", "strokes": strokes})
    try:
        while True:
            data = await websocket.receive_json()
            t = data.get("type")
            if t == "point":
                strokes.setdefault(data["id"], []).append(data["p"])
            elif t == "delete":
                strokes.pop(data["id"],None)
                await save_state(board_id)
            elif t == "clear":
                strokes.clear()
                await save_state(board_id)
            elif t == "end":
                await save_state(board_id)
                continue            
            await manager.broadcast(board_id, data, websocket)
    except WebSocketDisconnect:
        manager.disconnect(board_id, websocket)
        if board_id not in manager.rooms:
            await save_state(board_id)
            states.pop(board_id, None)




