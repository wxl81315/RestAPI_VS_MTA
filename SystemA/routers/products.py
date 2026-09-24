from __future__ import annotations
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import crud
import schemas
from database import get_db

router = APIRouter(prefix="/products", tags=["Products"])


@router.post("", response_model=schemas.ProductResponse)
def create_product(data: schemas.ProductCreate, db: Session = Depends(get_db)):
    """Create product"""
    return crud.create_product(db, data)


@router.get("", response_model=List[schemas.ProductResponse])
def list_products(
    name: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """List products with optional name filter."""
    return crud.search_products(db, name=name, skip=skip, limit=limit)


@router.get("/{product_id}", response_model=schemas.ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    """Get product"""
    return crud.get_product(db, product_id)


@router.put("/{product_id}", response_model=schemas.ProductResponse)
def update_product(product_id: int, data: schemas.ProductUpdate, db: Session = Depends(get_db)):
    """Update product"""
    return crud.update_product(db, product_id, data)


@router.delete("/{product_id}", response_model=schemas.ProductResponse)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """Delete product"""
    return crud.delete_product(db, product_id)
