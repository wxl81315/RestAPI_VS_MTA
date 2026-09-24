from __future__ import annotations
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import crud
import schemas
from database import get_db

router = APIRouter(tags=["Refunds"])


@router.post("/orders/{order_id}/refund", response_model=schemas.RefundResponse)
def create_refund(order_id: int, data: schemas.RefundCreate, db: Session = Depends(get_db)):
    """Create refund"""
    return crud.create_refund(db, order_id, data)


@router.get("/refunds", response_model=List[schemas.RefundResponse])
def list_refunds(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    """List refunds"""
    return crud.get_refunds(db, skip, limit)


@router.get("/refunds/{refund_id}", response_model=schemas.RefundResponse)
def get_refund(refund_id: int, db: Session = Depends(get_db)):
    """Get refund"""
    return crud.get_refund(db, refund_id)


@router.post("/refunds/{refund_id}/approve", response_model=schemas.RefundResponse)
def approve_refund(refund_id: int, db: Session = Depends(get_db)):
    """Approve refund"""
    return crud.approve_refund(db, refund_id)


@router.post("/refunds/{refund_id}/reject", response_model=schemas.RefundResponse)
def reject_refund(refund_id: int, db: Session = Depends(get_db)):
    """Reject refund"""
    return crud.reject_refund(db, refund_id)
