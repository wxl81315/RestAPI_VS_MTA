from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0)
    status = Column(String(20), default="NORMAL")  # NORMAL / LOCKED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_no = Column(String(32), unique=True, nullable=False, index=True)
    customer_name = Column(String(100), nullable=False)
    customer_email = Column(String(200), default="")
    status = Column(String(20), default="pending")
    total_amount = Column(Float, default=0.0)
    shipping_address = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    items = relationship("OrderItem", back_populates="order")
    refunds = relationship("Refund", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")


class Refund(Base):
    __tablename__ = "refunds"

    id = Column(Integer, primary_key=True, index=True)
    refund_no = Column(String(32), unique=True, nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    reason = Column(Text, default="")
    amount = Column(Float, nullable=False)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    order = relationship("Order", back_populates="refunds")
