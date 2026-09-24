import uuid
from sqlalchemy.orm import Session
from fastapi import HTTPException

import models
import schemas


# ==================== Product ====================
# 注意：本模块刻意 NOT 实现业务级校验（负价格、LOCKED 删除拦截、
# 重名检测等）。这正是传统 MVC 后端的真实写照——把"业务正确性"
# 的责任完全推给客户端 / Agent。当 Agent 传入脏数据时，DB 会
# 老老实实保存它，从而暴露 MVC 风格的危害。

def create_product(db: Session, data: schemas.ProductCreate):
    """创建商品。无业务校验：负价格也会被写入！"""
    product = models.Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def get_products(db: Session, skip: int = 0, limit: int = 20):
    return db.query(models.Product).offset(skip).limit(limit).all()


def search_products(db: Session, name: str = None, skip: int = 0, limit: int = 20):
    """按名称模糊搜索商品。"""
    q = db.query(models.Product)
    if name:
        q = q.filter(models.Product.name.contains(name))
    return q.offset(skip).limit(limit).all()


def get_product(db: Session, product_id: int):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Not found")
    return product


def update_product(db: Session, product_id: int, data: schemas.ProductUpdate):
    """部分更新商品。无业务校验：name='', price=-10 都会被写入。"""
    product = get_product(db, product_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return product


def delete_product(db: Session, product_id: int):
    """删除商品。无业务校验：LOCKED 商品也会被删！"""
    product = get_product(db, product_id)
    db.delete(product)
    db.commit()
    return product


# ==================== Order ====================

def create_order(db: Session, data: schemas.OrderCreate):
    if not data.items:
        raise HTTPException(status_code=400, detail="Bad request")

    order_no = uuid.uuid4().hex[:8].upper()
    total = 0.0
    order_items = []

    for item_data in data.items:
        product = db.query(models.Product).filter(models.Product.id == item_data.product_id).first()
        if not product:
            raise HTTPException(status_code=400, detail="Bad request")
        if product.stock < item_data.quantity:
            raise HTTPException(status_code=400, detail="Bad request")

        product.stock -= item_data.quantity
        unit_price = product.price
        total += unit_price * item_data.quantity
        order_items.append(models.OrderItem(
            product_id=item_data.product_id,
            quantity=item_data.quantity,
            unit_price=unit_price,
        ))

    order = models.Order(
        order_no=order_no,
        customer_name=data.customer_name,
        customer_email=data.customer_email or "",
        shipping_address=data.shipping_address or "",
        total_amount=total,
        status="pending",
    )
    order.items = order_items

    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def get_orders(db: Session, skip: int = 0, limit: int = 20, status: str = None):
    q = db.query(models.Order)
    if status:
        q = q.filter(models.Order.status == status)
    return q.order_by(models.Order.id.desc()).offset(skip).limit(limit).all()


def get_order(db: Session, order_id: int):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Not found")
    return order


def update_order(db: Session, order_id: int, data: schemas.OrderUpdate):
    order = get_order(db, order_id)
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="Bad request")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(order, key, value)
    db.commit()
    db.refresh(order)
    return order


def pay_order(db: Session, order_id: int):
    order = get_order(db, order_id)
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="Bad request")
    order.status = "paid"
    db.commit()
    db.refresh(order)
    return order


def ship_order(db: Session, order_id: int):
    order = get_order(db, order_id)
    if order.status != "paid":
        raise HTTPException(status_code=400, detail="Bad request")
    order.status = "shipped"
    db.commit()
    db.refresh(order)
    return order


def deliver_order(db: Session, order_id: int):
    order = get_order(db, order_id)
    if order.status != "shipped":
        raise HTTPException(status_code=400, detail="Bad request")
    order.status = "delivered"
    db.commit()
    db.refresh(order)
    return order


def cancel_order(db: Session, order_id: int):
    order = get_order(db, order_id)
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="Bad request")

    # Restore stock
    for item in order.items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        if product:
            product.stock += item.quantity

    order.status = "cancelled"
    db.commit()
    db.refresh(order)
    return order


# ==================== Refund ====================

def create_refund(db: Session, order_id: int, data: schemas.RefundCreate):
    order = get_order(db, order_id)
    if order.status not in ("paid", "shipped", "delivered"):
        raise HTTPException(status_code=400, detail="Bad request")
    if data.amount > order.total_amount:
        raise HTTPException(status_code=400, detail="Bad request")

    refund_no = "R" + uuid.uuid4().hex[:7].upper()
    order.status = "refund_pending"

    refund = models.Refund(
        refund_no=refund_no,
        order_id=order_id,
        reason=data.reason,
        amount=data.amount,
        status="pending",
    )
    db.add(refund)
    db.commit()
    db.refresh(refund)
    return refund


def get_refunds(db: Session, skip: int = 0, limit: int = 20):
    return db.query(models.Refund).order_by(models.Refund.id.desc()).offset(skip).limit(limit).all()


def get_refund(db: Session, refund_id: int):
    refund = db.query(models.Refund).filter(models.Refund.id == refund_id).first()
    if not refund:
        raise HTTPException(status_code=404, detail="Not found")
    return refund


def approve_refund(db: Session, refund_id: int):
    refund = get_refund(db, refund_id)
    if refund.status != "pending":
        raise HTTPException(status_code=400, detail="Bad request")

    refund.status = "approved"
    order = get_order(db, refund.order_id)
    order.status = "refunded"

    # Restore stock
    for item in order.items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        if product:
            product.stock += item.quantity

    db.commit()
    db.refresh(refund)
    return refund


def reject_refund(db: Session, refund_id: int):
    refund = get_refund(db, refund_id)
    if refund.status != "pending":
        raise HTTPException(status_code=400, detail="Bad request")

    refund.status = "rejected"

    # Restore the order to its previous status before refund_pending.
    # Since we don't track the previous status, default to "paid".
    order = get_order(db, refund.order_id)
    order.status = "paid"

    db.commit()
    db.refresh(refund)
    return refund
