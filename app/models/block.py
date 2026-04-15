# Pydantic models for request/response validation and serialization.

from __future__ import annotations
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ── Block Types ───────────────────────────────────────────────────────────────

BlockType = Literal["genesis", "order", "payment"]


# ── Request Payloads ──────────────────────────────────────────────────────────

class OrderBlockRequest(BaseModel):
    """Payload for POST /blockchain/order"""
    order_id:    str   = Field(..., min_length=1, max_length=128, examples=["ORD-123"])
    user_id:     str   = Field(..., min_length=1, max_length=128, examples=["U-001"])
    items:       list[dict[str, Any]] = Field(..., min_length=1)
    total_price: float = Field(..., gt=0, description="Order total in smallest currency unit")
    status:      str   = Field(..., examples=["PENDING", "PAID", "CANCELLED"])

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"PENDING", "PAID", "CANCELLED", "PROCESSING"}
        if v.upper() not in allowed:
            raise ValueError(f"status must be one of: {allowed}")
        return v.upper()


class PaymentBlockRequest(BaseModel):
    """Payload for POST /blockchain/payment"""
    payment_id:     str   = Field(..., min_length=1, max_length=128, examples=["PAY-456"])
    order_id:       str   = Field(..., min_length=1, max_length=128, examples=["ORD-123"])
    user_id:        str   = Field(..., min_length=1, max_length=128, examples=["U-001"])
    amount:         float = Field(..., gt=0, description="Payment amount in smallest currency unit")
    payment_method: str   = Field(..., examples=["QRIS", "TRANSFER", "CARD"])
    status:         str   = Field(..., examples=["SUCCESS", "FAILED", "PENDING"])

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"SUCCESS", "FAILED", "PENDING", "REFUNDED"}
        if v.upper() not in allowed:
            raise ValueError(f"status must be one of: {allowed}")
        return v.upper()

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, v: str) -> str:
        allowed = {"QRIS", "TRANSFER", "CARD", "WALLET", "COD"}
        if v.upper() not in allowed:
            raise ValueError(f"payment_method must be one of: {allowed}")
        return v.upper()


# ── Block Data Model ──────────────────────────────────────────────────────────

class Block(BaseModel):
    """In-memory block representation."""
    index:         int
    timestamp:     str
    block_type:    BlockType
    data:          dict[str, Any]
    previous_hash: str
    hash:          str

    model_config = {"frozen": True}   # immutable after creation


# ── Response Models ───────────────────────────────────────────────────────────

class BlockResponse(BaseModel):
    index:         int
    timestamp:     str
    block_type:    str
    data:          dict[str, Any]
    previous_hash: str
    hash:          str
    created_at:    Optional[datetime] = None


class ChainResponse(BaseModel):
    length: int
    chain:  list[BlockResponse]


class ValidationResponse(BaseModel):
    valid:   bool
    message: str
    checked: int   # number of blocks checked


class VerifyResponse(BaseModel):
    found:     bool
    status:    str   # "VALID" | "TAMPERED" | "NOT_FOUND"
    message:   str
    block:     Optional[BlockResponse] = None


class AddBlockResponse(BaseModel):
    success: bool
    message: str
    block:   BlockResponse