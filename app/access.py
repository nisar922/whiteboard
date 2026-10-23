from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Board ,BoardMember

async def has_access(db: AsyncSession,board:Board | None , user_id: int) -> bool:
    if not board:
        return False
    if board.owner_id == user_id:
        return True
    result = await db.execute(
        select(BoardMember).where(
            BoardMember.board_id == board.id,
            BoardMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none is not None