from __future__ import annotations
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import crud
import schemas
from database import get_db

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("", response_model=schemas.OrderResponse)
def create_order(data: schemas.OrderCreate, db: Session = Depends(get_db)):
    """Create order"""
    return crud.create_order(db, data)


@router.get("", response_model=List[schemas.OrderListResponse])
def list_orders(skip: int = 0, limit: int = 20, status: str = None, db: Session = Depends(get_db)):
    """List orders"""
    return crud.get_orders(db, skip, limit, status)


@router.get("/{order_id}", response_model=schemas.OrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)):
    """Get order by ID"""
    return crud.get_order(db, order_id)


@router.put("/{order_id}", response_model=schemas.OrderResponse)
def update_order(order_id: int, data: schemas.OrderUpdate, db: Session = Depends(get_db)):
    """Update order"""
    return crud.update_order(db, order_id, data)


@router.post("/{order_id}/pay", response_model=schemas.OrderResponse)
def pay_order(order_id: int, db: Session = Depends(get_db)):
    """Pay order"""
    return crud.pay_order(db, order_id)


@router.post("/{order_id}/ship", response_model=schemas.OrderResponse)
def ship_order(order_id: int, db: Session = Depends(get_db)):
    """Ship order"""
    return crud.ship_order(db, order_id)


@router.post("/{order_id}/deliver", response_model=schemas.OrderResponse)
def deliver_order(order_id: int, db: Session = Depends(get_db)):
    """Confirm delivery"""
    return crud.deliver_order(db, order_id)


@router.post("/{order_id}/cancel", response_model=schemas.OrderResponse)
def cancel_order(order_id: int, db: Session = Depends(get_db)):
    """Cancel order"""
    return crud.cancel_order(db, order_id)
