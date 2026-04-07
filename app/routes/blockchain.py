# app/routes/blockchain.py
# FastAPI router for all /blockchain/* endpoints.

import time
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.models.block import (
    OrderBlockRequest,
    DeploymentBlockRequest,
    AddBlockResponse,
    ChainResponse,
    ValidationResponse,
    VerifyResponse,
    BlockResponse,
)
from app.services.blockchain import (
    get_blockchain,
    DuplicateEntryError,
    BlockchainError,
)
from app.utils.logger import get_logger
from app.utils.metrics import (
    blockchain_operations_total,
    chain_validation_duration_seconds,
    chain_valid,
    blocks_total,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/blockchain", tags=["Blockchain"])


def _block_to_response(block) -> BlockResponse:
    return BlockResponse(
        index=block.index,
        timestamp=block.timestamp,
        block_type=block.block_type,
        data=block.data,
        previous_hash=block.previous_hash,
        hash=block.hash,
    )


# ── Add Order Block ───────────────────────────────────────────────────────────

@router.post(
    "/order",
    response_model=AddBlockResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an order block to the blockchain",
    description="Records an order transaction on the blockchain. order_id must be unique.",
)
async def add_order_block(
    payload: OrderBlockRequest,
    session: AsyncSession = Depends(get_session),
):
    bc = get_blockchain()
    try:
        block = await bc.add_order_block(payload.model_dump(), session)
        blocks_total.set(bc.length)
        blockchain_operations_total.labels(
            operation="add", block_type="order", status="success"
        ).inc()

        logger.info("api_add_order_block", order_id=payload.order_id, index=block.index)
        return AddBlockResponse(
            success=True,
            message=f"Order '{payload.order_id}' recorded on blockchain at index {block.index}",
            block=_block_to_response(block),
        )

    except DuplicateEntryError as e:
        blockchain_operations_total.labels(
            operation="add", block_type="order", status="duplicate"
        ).inc()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    except BlockchainError as e:
        blockchain_operations_total.labels(
            operation="add", block_type="order", status="error"
        ).inc()
        logger.error("api_add_order_block_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ── Add Deployment Block ──────────────────────────────────────────────────────

@router.post(
    "/deployment",
    response_model=AddBlockResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a deployment verification block",
    description="Records a DevSecOps deployment event on the blockchain including scan results.",
)
async def add_deployment_block(
    payload: DeploymentBlockRequest,
    session: AsyncSession = Depends(get_session),
):
    bc = get_blockchain()
    try:
        block = await bc.add_deployment_block(payload.model_dump(), session)
        blocks_total.set(bc.length)
        blockchain_operations_total.labels(
            operation="add", block_type="deployment", status="success"
        ).inc()

        logger.info(
            "api_add_deployment_block",
            service=payload.service,
            commit=payload.commit_hash,
            index=block.index,
        )
        return AddBlockResponse(
            success=True,
            message=f"Deployment of '{payload.service}' recorded at index {block.index}",
            block=_block_to_response(block),
        )

    except BlockchainError as e:
        blockchain_operations_total.labels(
            operation="add", block_type="deployment", status="error"
        ).inc()
        logger.error("api_add_deployment_block_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ── Get Full Chain ────────────────────────────────────────────────────────────

@router.get(
    "/chain",
    response_model=ChainResponse,
    summary="Get the full blockchain",
    description="Returns all blocks in order from genesis to latest.",
)
async def get_chain():
    bc = get_blockchain()
    return ChainResponse(
        length=bc.length,
        chain=[_block_to_response(b) for b in bc.chain],
    )


# ── Validate Chain Integrity ──────────────────────────────────────────────────

@router.get(
    "/validate",
    response_model=ValidationResponse,
    summary="Validate entire chain integrity",
    description="Recomputes all block hashes and verifies chain linkage. Returns valid/invalid.",
)
async def validate_chain():
    bc = get_blockchain()
    start = time.perf_counter()

    is_valid, message, checked = bc.validate_chain()

    duration = time.perf_counter() - start
    chain_validation_duration_seconds.observe(duration)
    chain_valid.set(1 if is_valid else 0)

    blockchain_operations_total.labels(
        operation="validate",
        block_type="chain",
        status="valid" if is_valid else "invalid",
    ).inc()

    logger.info(
        "chain_validated",
        valid=is_valid,
        blocks_checked=checked,
        duration_ms=round(duration * 1000, 2),
    )

    return ValidationResponse(valid=is_valid, message=message, checked=checked)


# ── Verify Order ──────────────────────────────────────────────────────────────

@router.get(
    "/verify/order/{order_id}",
    response_model=VerifyResponse,
    summary="Verify order integrity on the blockchain",
    description="Checks if an order exists and its data has not been tampered with.",
)
async def verify_order(order_id: str):
    bc = get_blockchain()
    found, block = bc.verify_order(order_id)

    blockchain_operations_total.labels(
        operation="verify",
        block_type="order",
        status="found" if block else "not_found",
    ).inc()

    if block is None:
        return VerifyResponse(
            found=False,
            status="NOT_FOUND",
            message=f"No blockchain record found for order '{order_id}'",
        )

    status_str = "VALID" if found else "TAMPERED"
    message    = (
        f"Order '{order_id}' blockchain record is VALID — data integrity confirmed"
        if found
        else f"Order '{order_id}' blockchain record is TAMPERED — hash mismatch detected"
    )

    logger.info("order_verified", order_id=order_id, status=status_str)

    return VerifyResponse(
        found=True,
        status=status_str,
        message=message,
        block=_block_to_response(block),
    )


# ── Verify Deployment ─────────────────────────────────────────────────────────

@router.get(
    "/verify/deployment/{service}",
    response_model=VerifyResponse,
    summary="Verify latest deployment integrity for a service",
    description="Checks if the most recent deployment of a service exists and has not been tampered.",
)
async def verify_deployment(service: str):
    bc = get_blockchain()
    found, block = bc.verify_deployment(service)

    blockchain_operations_total.labels(
        operation="verify",
        block_type="deployment",
        status="found" if block else "not_found",
    ).inc()

    if block is None:
        return VerifyResponse(
            found=False,
            status="NOT_FOUND",
            message=f"No deployment record found for service '{service}'",
        )

    status_str = "VALID" if found else "TAMPERED"
    message    = (
        f"Latest deployment of '{service}' is VALID — integrity confirmed"
        if found
        else f"Latest deployment of '{service}' is TAMPERED — hash mismatch detected"
    )

    logger.info("deployment_verified", service=service, status=status_str)

    return VerifyResponse(
        found=True,
        status=status_str,
        message=message,
        block=_block_to_response(block),
    )


# ── Get Deployment History ────────────────────────────────────────────────────

@router.get(
    "/history/deployment/{service}",
    summary="Get full deployment history for a service",
    description="Returns all deployment blocks for a service, oldest first.",
)
async def get_deployment_history(service: str):
    bc = get_blockchain()
    deployments = bc.get_all_deployments(service)

    if not deployments:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No deployment history found for service '{service}'",
        )

    return {
        "service": service,
        "total":   len(deployments),
        "history": [_block_to_response(b) for b in deployments],
    }