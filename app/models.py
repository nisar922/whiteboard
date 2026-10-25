from sqlalchemy import String, ForeignKey, DateTime, func, Boolean,text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB

class User(Base):
    __tablename__="users"

    id:Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))


class Board(Base):
    __tablename__ ="boards"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column((String(255)))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    join_code: Mapped[str] = mapped_column(String(8), unique=True)
    default_can_edit: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    state: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )   

class BoardMember(Base):
    __tablename__="board_members"

    board_id: Mapped[int] = mapped_column(
        ForeignKey("boards.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )
    can_edit: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true") 
    )