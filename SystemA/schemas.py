from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


# ---------- Product ----------

class ProductCreate(BaseModel):
    """严格模式：禁止额外字段，price 类型必须为 float。
    这模拟典型 MVC 后端：只暴露字段名，不解释业务规则。"""
    model_config = ConfigDict(extra="forbid")

    name: str
    description: Optional[str] = ""
    price: float
    stock: Optional[int] = 0


class ProductUpdate(BaseModel):
    """严格模式：禁止额外字段。"""
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None
    status: Optional[str] = None


class ProductResponse(BaseModel):
    id: int
    name: str
    description: str
    price: float
    stock: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- OrderItem ----------

class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    unit_price: float

    model_config = {"from_attributes": True}


# ---------- Order ----------

class OrderCreate(BaseModel):
    customer_name: str
    customer_email: Optional[str] = ""
    shipping_address: Optional[str] = ""
    items: List[OrderItemCreate]


class OrderUpdate(BaseModel):
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    shipping_address: Optional[str] = None


class OrderResponse(BaseModel):
    id: int
    order_no: str
    customer_name: str
    customer_email: str
    status: str
    total_amount: float
    shipping_address: str
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemResponse] = []

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    id: int
    order_no: str
    customer_name: str
    status: str
    total_amount: float
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Refund ----------

class RefundCreate(BaseModel):
    reason: str
    amount: float


class RefundResponse(BaseModel):
    id: int
    refund_no: str
    order_id: int
    reason: str
    amount: float
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
