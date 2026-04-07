# Core blockchain implementation.
# Hash formula: SHA256(index + timestamp + type + canonical_json(data) + previous_hash)

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.block import Block, BlockType
from app.db.models import BlockRecord
from app.utils.logger import get_logger

logger = get_logger(__name__)

GENESIS_HASH = "0" * 64   # conventional genesis previous_hash


class BlockchainError(Exception):
    pass


class DuplicateEntryError(BlockchainError):
    pass


class Blockchain:
    """
    Lightweight append-only blockchain.
    Thread-safety: this implementation is single-process safe (asyncio).
    For multi-replica deployments, use DB as the authoritative lock.
    """

    def __init__(self) -> None:
        self._chain: list[Block] = []
        # In-memory index for fast O(1) lookups by order_id and service
        self._order_index:      dict[str, Block] = {}
        self._deployment_index: dict[str, list[Block]] = {}

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def chain(self) -> list[Block]:
        return list(self._chain)   # return copy to prevent external mutation

    @property
    def length(self) -> int:
        return len(self._chain)

    @property
    def last_block(self) -> Optional[Block]:
        return self._chain[-1] if self._chain else None

    # ── Hashing ───────────────────────────────────────────────────────────────

    @staticmethod
    def calculate_hash(
        index: int,
        timestamp: str,
        block_type: str,
        data: dict,
        previous_hash: str,
    ) -> str:
        """
        Compute SHA256 hash of block contents.
        Uses canonical JSON (sorted keys) to ensure deterministic output
        regardless of dict insertion order.
        """
        raw = (
            str(index)
            + timestamp
            + block_type
            + json.dumps(data, sort_keys=True, ensure_ascii=True)
            + previous_hash
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # ── Genesis Block ─────────────────────────────────────────────────────────

    def _create_genesis_block(self) -> Block:
        timestamp = datetime.now(timezone.utc).isoformat()
        data      = {"message": "Genesis Block — Blockchain initialized"}
        hash_val  = self.calculate_hash(0, timestamp, "genesis", data, GENESIS_HASH)

        return Block(
            index=0,
            timestamp=timestamp,
            block_type="genesis",
            data=data,
            previous_hash=GENESIS_HASH,
            hash=hash_val,
        )

    # ── Add Block ─────────────────────────────────────────────────────────────

    def _build_block(self, data: dict, block_type: BlockType) -> Block:
        """Create a new block linked to the current chain tip."""
        prev = self.last_block
        if prev is None:
            raise BlockchainError("Chain is empty — genesis block missing")

        index     = len(self._chain)
        timestamp = datetime.now(timezone.utc).isoformat()
        hash_val  = self.calculate_hash(index, timestamp, block_type, data, prev.hash)

        return Block(
            index=index,
            timestamp=timestamp,
            block_type=block_type,
            data=data,
            previous_hash=prev.hash,
            hash=hash_val,
        )

    def _append_to_memory(self, block: Block) -> None:
        """Add block to in-memory chain and update lookup indexes."""
        self._chain.append(block)

        if block.block_type == "order":
            order_id = block.data.get("order_id")
            if order_id:
                self._order_index[str(order_id)] = block

        elif block.block_type == "deployment":
            service = block.data.get("service")
            if service:
                self._deployment_index.setdefault(str(service), []).append(block)

    # ── Public API ────────────────────────────────────────────────────────────

    async def initialize(self, session: AsyncSession) -> None:
        """
        Load existing chain from PostgreSQL on startup.
        If DB is empty, create and persist the genesis block.
        """
        result = await session.execute(
            select(BlockRecord).order_by(BlockRecord.index)
        )
        records = result.scalars().all()

        if not records:
            # First ever boot — create genesis block
            genesis = self._create_genesis_block()
            self._append_to_memory(genesis)
            session.add(self._block_to_record(genesis))
            await session.commit()
            logger.info("blockchain_initialized", blocks=1, source="genesis")
        else:
            # Restore chain from DB
            for rec in records:
                block = Block(
                    index=rec.index,
                    timestamp=rec.timestamp,
                    block_type=rec.block_type,
                    data=rec.data,
                    previous_hash=rec.previous_hash,
                    hash=rec.hash,
                )
                self._append_to_memory(block)
            logger.info("blockchain_restored", blocks=len(records), source="database")

    async def add_order_block(self, data: dict, session: AsyncSession) -> Block:
        """
        Add an order block. Prevents duplicate order_id entries.
        """
        order_id = str(data.get("order_id", ""))
        if order_id in self._order_index:
            raise DuplicateEntryError(
                f"Order '{order_id}' already exists in the blockchain"
            )

        block = self._build_block(data, "order")
        self._append_to_memory(block)

        session.add(self._block_to_record(block))
        await session.commit()

        logger.info(
            "block_added",
            block_type="order",
            index=block.index,
            order_id=order_id,
            hash=block.hash[:16],
        )
        return block

    async def add_deployment_block(self, data: dict, session: AsyncSession) -> Block:
        """
        Add a deployment block. Multiple deployments of the same service are allowed
        (deployment history is valuable — do not deduplicate).
        """
        block = self._build_block(data, "deployment")
        self._append_to_memory(block)

        session.add(self._block_to_record(block))
        await session.commit()

        logger.info(
            "block_added",
            block_type="deployment",
            index=block.index,
            service=data.get("service"),
            hash=block.hash[:16],
        )
        return block

    # ── Validation ────────────────────────────────────────────────────────────

    def validate_chain(self) -> tuple[bool, str, int]:
        """
        Validate the entire chain by:
          1. Recomputing each block's hash and comparing
          2. Verifying each block's previous_hash matches the prior block's hash

        Returns: (is_valid, message, blocks_checked)
        """
        if not self._chain:
            return False, "Chain is empty", 0

        # Validate genesis block
        genesis = self._chain[0]
        expected = self.calculate_hash(
            genesis.index,
            genesis.timestamp,
            genesis.block_type,
            genesis.data,
            genesis.previous_hash,
        )
        if genesis.hash != expected:
            return False, f"Genesis block hash is invalid at index 0", 1

        # Validate subsequent blocks
        for i in range(1, len(self._chain)):
            current  = self._chain[i]
            previous = self._chain[i - 1]

            # 1. Verify current block's hash
            recomputed = self.calculate_hash(
                current.index,
                current.timestamp,
                current.block_type,
                current.data,
                current.previous_hash,
            )
            if current.hash != recomputed:
                return (
                    False,
                    f"Block {i} hash is invalid — data may have been tampered",
                    i + 1,
                )

            # 2. Verify chain linkage
            if current.previous_hash != previous.hash:
                return (
                    False,
                    f"Block {i} previous_hash does not match block {i-1} hash — chain is broken",
                    i + 1,
                )

        return True, "Chain is valid", len(self._chain)

    # ── Verification ─────────────────────────────────────────────────────────

    def verify_order(self, order_id: str) -> tuple[bool, Optional[Block]]:
        """
        Verify that an order exists in the blockchain and has not been tampered with.
        Returns (found, block).
        """
        block = self._order_index.get(str(order_id))
        if not block:
            return False, None

        # Recompute hash to detect tampering
        recomputed = self.calculate_hash(
            block.index,
            block.timestamp,
            block.block_type,
            block.data,
            block.previous_hash,
        )
        return recomputed == block.hash, block

    def verify_deployment(self, service: str) -> tuple[bool, Optional[Block]]:
        """
        Verify the most recent deployment block for a service.
        Returns (found, latest_block).
        """
        deployments = self._deployment_index.get(str(service))
        if not deployments:
            return False, None

        block = deployments[-1]   # most recent deployment
        recomputed = self.calculate_hash(
            block.index,
            block.timestamp,
            block.block_type,
            block.data,
            block.previous_hash,
        )
        return recomputed == block.hash, block

    def get_all_deployments(self, service: str) -> list[Block]:
        """Return full deployment history for a service."""
        return list(self._deployment_index.get(str(service), []))

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _block_to_record(block: Block) -> BlockRecord:
        return BlockRecord(
            index=block.index,
            timestamp=block.timestamp,
            block_type=block.block_type,
            data=block.data,
            previous_hash=block.previous_hash,
            hash=block.hash,
        )


# ── Singleton — shared across the FastAPI app ─────────────────────────────────

_blockchain: Optional[Blockchain] = None


def get_blockchain() -> Blockchain:
    if _blockchain is None:
        raise RuntimeError("Blockchain not initialized. Call init_blockchain() first.")
    return _blockchain


async def init_blockchain(session: AsyncSession) -> Blockchain:
    global _blockchain
    _blockchain = Blockchain()
    await _blockchain.initialize(session)
    return _blockchain