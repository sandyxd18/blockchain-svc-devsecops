# Pydantic models for request/response validation and serialization.

from __future__ import annotations
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ── Block Types ───────────────────────────────────────────────────────────────

BlockType = Literal["order", "deployment"]


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


class DeploymentBlockRequest(BaseModel):
    """Payload for POST /blockchain/deployment"""
    service:      str  = Field(..., min_length=1, max_length=128, examples=["order-service"])
    image_digest: str  = Field(..., min_length=1, description="Container image digest (sha256:...)")
    commit_hash:  str  = Field(..., min_length=7, max_length=64, examples=["abc1234"])
    sast:         str  = Field(..., examples=["PASS", "FAIL"])
    trivy:        str  = Field(..., examples=["PASS", "FAIL"])
    dast:         str  = Field(..., examples=["PASS", "FAIL"])
    deployed_by:  Optional[str] = Field(None, examples=["ci-pipeline"])
    environment:  Optional[str] = Field(None, examples=["production", "staging"])

    @field_validator("sast", "trivy", "dast")
    @classmethod
    def validate_scan_result(cls, v: str) -> str:
        allowed = {"PASS", "FAIL", "SKIPPED"}
        if v.upper() not in allowed:
            raise ValueError(f"Scan result must be one of: {allowed}")
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