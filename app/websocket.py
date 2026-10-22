from collections import defaultdict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from app.config import settings
from app.database import SessionLocal
from app.models import Board

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
    if not board or board.owner_id != user_id:
        await websocket.close(code=1008)
        return
    await manager.connect(board_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await manager.broadcast(board_id, data, websocket)
    except WebSocketDisconnect:
        manager.disconnect(board_id, websocket)