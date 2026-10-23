from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.access import has_access
from app.auth import get_current_user
from app.database import get_db
from app.models import Board, BoardMember, User
from app.schemas import BoardCreate, BoardOut, ShareRequest

router = APIRouter(prefix="/boards", tags=["boards"])


async def get_accessible_board(board_id: int, db: AsyncSession, user: User) -> Board:
    board = await db.get(Board, board_id)
    if not await has_access(db, board, user.id):
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
    member_ids = select(BoardMember.board_id).where(BoardMember.user_id == user.id)
    result = await db.execute(
        select(Board).where(or_(Board.owner_id == user.id, Board.id.in_(member_ids)))
    )
    return result.scalars().all()

@router.get("/{board_id}", response_model=BoardOut)
async def get_board(board_id: int, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    return await get_accessible_board(board_id, db, user)


@router.post("/{board_id}/share", status_code=201)
async def share_board(board_id: int, data: ShareRequest,
                      db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    board = await db.get(Board, board_id)
    if not board or board.owner_id != user.id:
        raise HTTPException(404, "Board not found")
    result = await db.execute(select(User).where(User.email == data.email))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "User not found")
    if target.id == user.id:
        raise HTTPException(400, "You already own this board")
    if not await db.get(BoardMember, (board_id, target.id)):
        db.add(BoardMember(board_id=board_id, user_id=target.id))
        await db.commit()
    return {"detail": f"Shared with {data.email}"}


@router.delete("/{board_id}", status_code=204)
async def delete_board(board_id: int, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    board = await db.get(Board, board_id)
    if not board or board.owner_id != user.id:
        raise HTTPException(404, "Board not found")
    await db.delete(board)
    await db.commit()


    