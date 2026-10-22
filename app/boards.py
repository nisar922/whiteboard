from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Board, User
from app.schemas import BoardCreate, BoardOut
from app.auth import get_current_user

router = APIRouter(prefix="/boards", tags=["boards"])

async def get_own_board(board_id: int, db: AsyncSession, user: User) -> Board:
    board = await db.get(Board, board_id)
    if not board or board.owner_id != user.id:
        raise HTTPException(404, "Board not found")
    return board

@router.post("", response_model=BoardOut, status_code=201)
async def create_board(data: BoardCreate, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    board = Board(title=data.title, owner_id=user.id)
    db.add(board)
    await db.commit()
    await db.refresh(board)
    return board

@router.get("", response_model=list[BoardOut])
async def list_boards(db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    result = await db.execute(select(Board).where(Board.owner_id == user.id))
    return result.scalars().all()

@router.get("/{board_id}", response_model=BoardOut)
async def get_board(board_id: int, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    return await get_own_board(board_id, db, user)

@router.delete("/{board_id}", status_code=204)
async def delete_board(board_id: int, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    board = await get_own_board(board_id, db, user)
    await db.delete(board)
    await db.commit()

    