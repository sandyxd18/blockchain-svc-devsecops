# SQLAlchemy ORM model for blockchain_blocks table.

from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class BlockRecord(Base):
    """
    Persisted representation of a blockchain block.
    Stored in PostgreSQL for durability and auditability.
    In-memory chain is the authoritative source; DB is the persistence layer.
    """
    __tablename__ = "blockchain_blocks"

    id            : Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    index         : Mapped[int]      = mapped_column(Integer, unique=True, nullable=False)
    timestamp     : Mapped[str]      = mapped_column(String(64), nullable=False)
    block_type    : Mapped[str]      = mapped_column(String(32), nullable=False)  # "order" | "deployment"
    data          : Mapped[dict]     = mapped_column(JSONB, nullable=False)
    previous_hash : Mapped[str]      = mapped_column(String(64), nullable=False)
    hash          : Mapped[str]      = mapped_column(String(64), nullable=False, unique=True)
    created_at    : Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        # Fast lookups by type (e.g. all order blocks)
        Index("ix_blocks_type",  "block_type"),
        # Fast lookups by hash (integrity checks)
        Index("ix_blocks_hash",  "hash"),
    )

    def __repr__(self) -> str:
        return f"<BlockRecord index={self.index} type={self.block_type} hash={self.hash[:8]}...>"