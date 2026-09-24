"""
Order Tools — MTA tool endpoints for order lifecycle management.
Each tool returns AgentResponse with explicit state, allowed next actions,
and error guidance following P1-P6 principles.
"""
from __future__ import annotations
import json, uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import models, schemas
from schemas import AgentResponse
from database import get_db
from state_machine import get_order_allowed_tools
from idempotency import check_idempotency, save_idempotency

router = APIRouter(prefix="/tools", tags=["Order Tools"])


def _order_data(order) -> dict:
    return schemas.OrderData.model_validate(order).model_dump(mode="json")


def _order_list_data(order) -> dict:
    return schemas.OrderListItemData.model_validate(order).model_dump(mode="json")


@router.post("/create_order", response_model=AgentResponse)
def create_order(input_data: schemas.CreateOrderInput, db: Session = Depends(get_db)):
    """Create a new order with one or more products.
    Before calling, verify each product_id exists and has sufficient stock via
    'get_product_details'. The customer_name and shipping_address should come
    from the user — do NOT guess them.
    **When to use**: After confirming products, quantities, and customer info with the user.
    **Returns**: The created order with order_no, status='pending', total_amount, and items."""
    cached = check_idempotency(db, input_data.idempotency_key)
    if cached:
        data = json.loads(cached)
        return AgentResponse(data=data, current_state="pending",
                             allowed_next_tools=get_order_allowed_tools("pending"), error_guidance=None)
    if not input_data.items:
        return AgentResponse(
            data=None, current_state="validation_error",
            allowed_next_tools=["create_order", "search_products"],
            error_guidance="The 'items' list is empty. An order must contain at least one item. "
                          "Use 'search_products' to find products, then include them in the items list.",
        )
    order_no = uuid.uuid4().hex[:8].upper()
    total = 0.0
    order_items = []
    for item in input_data.items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        if not product:
            return AgentResponse(
                data=None, current_state="validation_error",
                allowed_next_tools=["search_products", "get_product_details"],
                error_guidance=f"Product ID {item.product_id} does not exist. "
                              f"Use 'search_products' to find valid product IDs before creating an order.",
            )
        if product.stock < item.quantity:
            return AgentResponse(
                data={"product_id": item.product_id, "product_name": product.name,
                      "requested": item.quantity, "available_stock": product.stock},
                current_state="validation_error",
                allowed_next_tools=["get_product_details", "create_order"],
                error_guidance=f"Insufficient stock for '{product.name}' (ID: {item.product_id}). "
                              f"Requested {item.quantity} but only {product.stock} available. "
                              f"Ask the user to reduce the quantity or choose a different product.",
            )
        product.stock -= item.quantity
        total += product.price * item.quantity
        order_items.append(models.OrderItem(product_id=item.product_id,
                                            quantity=item.quantity, unit_price=product.price))
    order = models.Order(order_no=order_no, customer_name=input_data.customer_name,
                         customer_email=input_data.customer_email or "",
                         shipping_address=input_data.shipping_address or "",
                         total_amount=total, status="pending")
    order.items = order_items
    db.add(order)
    db.commit()
    db.refresh(order)
    result = _order_data(order)
    save_idempotency(db, input_data.idempotency_key, "create_order", json.dumps(result))
    return AgentResponse(data=result, current_state="pending",
                         allowed_next_tools=get_order_allowed_tools("pending"), error_guidance=None)


@router.post("/search_orders", response_model=AgentResponse)
def search_orders(input_data: schemas.SearchOrdersInput, db: Session = Depends(get_db)):
    """Search and list orders with optional filters.
    **When to use**: To find orders by status or customer name, or to browse recent orders.
    **Returns**: A list of order summary objects (id, order_no, customer_name, status, total_amount)."""
    q = db.query(models.Order)
    if input_data.status:
        valid = ["pending", "paid", "shipped", "delivered", "refund_pending", "refunded", "cancelled"]
        if input_data.status not in valid:
            return AgentResponse(
                data=None, current_state="validation_error",
                allowed_next_tools=["search_orders"],
                error_guidance=f"Invalid status '{input_data.status}'. Valid values are: {', '.join(valid)}.",
            )
        q = q.filter(models.Order.status == input_data.status)
    if input_data.customer_name:
        q = q.filter(models.Order.customer_name.contains(input_data.customer_name))
    orders = q.order_by(models.Order.id.desc()).offset(input_data.skip).limit(input_data.limit).all()
    orders_data = [_order_list_data(o) for o in orders]
    return AgentResponse(
        data={"orders": orders_data, "total_returned": len(orders_data)},
        current_state="list_result",
        allowed_next_tools=["get_order_details", "search_orders", "create_order"],
        error_guidance=None,
    )


@router.post("/get_order_details", response_model=AgentResponse)
def get_order_details(input_data: schemas.GetOrderDetailsInput, db: Session = Depends(get_db)):
    """Get full details of a specific order including items, status, and amounts.
    **When to use**: Before any state-changing operation (pay, ship, refund) to verify current status.
    **Returns**: Complete order object with items, status, total_amount, and timestamps."""
    order = db.query(models.Order).filter(models.Order.id == input_data.order_id).first()
    if not order:
        return AgentResponse(
            data=None, current_state="not_found",
            allowed_next_tools=["search_orders"],
            error_guidance=f"Order ID {input_data.order_id} not found. Use 'search_orders' to find valid IDs.",
        )
    return AgentResponse(
        data=_order_data(order), current_state=order.status,
        allowed_next_tools=get_order_allowed_tools(order.status), error_guidance=None,
    )


@router.post("/update_order", response_model=AgentResponse)
def update_order(input_data: schemas.UpdateOrderInput, db: Session = Depends(get_db)):
    """Update order details (customer name, email, address). Only works for 'pending' orders.
    **When to use**: When the user wants to correct order info before payment.
    **Returns**: The updated order object."""
    cached = check_idempotency(db, input_data.idempotency_key)
    if cached:
        data = json.loads(cached)
        return AgentResponse(data=data, current_state="pending",
                             allowed_next_tools=get_order_allowed_tools("pending"), error_guidance=None)
    order = db.query(models.Order).filter(models.Order.id == input_data.order_id).first()
    if not order:
        return AgentResponse(
            data=None, current_state="not_found", allowed_next_tools=["search_orders"],
            error_guidance=f"Order ID {input_data.order_id} not found. Use 'search_orders' to find valid IDs.",
        )
    if order.status != "pending":
        return AgentResponse(
            data=_order_data(order), current_state=order.status,
            allowed_next_tools=get_order_allowed_tools(order.status),
            error_guidance=f"Cannot update this order because its status is '{order.status}'. "
                          f"Only 'pending' orders can be updated. "
                          f"Current allowed actions: {get_order_allowed_tools(order.status)}.",
        )
    fields = input_data.model_dump(exclude_unset=True, exclude={"order_id", "idempotency_key"})
    for k, v in fields.items():
        if v is not None:
            setattr(order, k, v)
    db.commit()
    db.refresh(order)
    result = _order_data(order)
    save_idempotency(db, input_data.idempotency_key, "update_order", json.dumps(result))
    return AgentResponse(data=result, current_state="pending",
                         allowed_next_tools=get_order_allowed_tools("pending"), error_guidance=None)


@router.post("/pay_order", response_model=AgentResponse)
def pay_order(input_data: schemas.PayOrderInput, db: Session = Depends(get_db)):
    """Process payment for a pending order. Transitions status from 'pending' to 'paid'.
    **When to use**: After the user confirms they want to pay for the order.
    **Returns**: The order with updated status='paid'."""
    cached = check_idempotency(db, input_data.idempotency_key)
    if cached:
        data = json.loads(cached)
        return AgentResponse(data=data, current_state="paid",
                             allowed_next_tools=get_order_allowed_tools("paid"), error_guidance=None)
    order = db.query(models.Order).filter(models.Order.id == input_data.order_id).first()
    if not order:
        return AgentResponse(
            data=None, current_state="not_found", allowed_next_tools=["search_orders"],
            error_guidance=f"Order ID {input_data.order_id} not found. Use 'search_orders' to find valid IDs.",
        )
    if order.status != "pending":
        return AgentResponse(
            data=_order_data(order), current_state=order.status,
            allowed_next_tools=get_order_allowed_tools(order.status),
            error_guidance=f"Cannot pay this order because its status is '{order.status}', not 'pending'. "
                          f"Allowed actions for current state: {get_order_allowed_tools(order.status)}.",
        )
    order.status = "paid"
    db.commit()
    db.refresh(order)
    result = _order_data(order)
    save_idempotency(db, input_data.idempotency_key, "pay_order", json.dumps(result))
    return AgentResponse(data=result, current_state="paid",
                         allowed_next_tools=get_order_allowed_tools("paid"), error_guidance=None)


@router.post("/ship_order", response_model=AgentResponse)
def ship_order(input_data: schemas.ShipOrderInput, db: Session = Depends(get_db)):
    """Ship a paid order. Transitions status from 'paid' to 'shipped'.
    **When to use**: After payment is confirmed and the order is ready for shipment.
    **Returns**: The order with updated status='shipped'."""
    cached = check_idempotency(db, input_data.idempotency_key)
    if cached:
        data = json.loads(cached)
        return AgentResponse(data=data, current_state="shipped",
                             allowed_next_tools=get_order_allowed_tools("shipped"), error_guidance=None)
    order = db.query(models.Order).filter(models.Order.id == input_data.order_id).first()
    if not order:
        return AgentResponse(
            data=None, current_state="not_found", allowed_next_tools=["search_orders"],
            error_guidance=f"Order ID {input_data.order_id} not found.",
        )
    if order.status != "paid":
        return AgentResponse(
            data=_order_data(order), current_state=order.status,
            allowed_next_tools=get_order_allowed_tools(order.status),
            error_guidance=f"Cannot ship: order status is '{order.status}', must be 'paid'. "
                          f"{'Use pay_order first.' if order.status == 'pending' else ''}",
        )
    order.status = "shipped"
    db.commit()
    db.refresh(order)
    result = _order_data(order)
    save_idempotency(db, input_data.idempotency_key, "ship_order", json.dumps(result))
    return AgentResponse(data=result, current_state="shipped",
                         allowed_next_tools=get_order_allowed_tools("shipped"), error_guidance=None)


@router.post("/confirm_delivery", response_model=AgentResponse)
def confirm_delivery(input_data: schemas.ConfirmDeliveryInput, db: Session = Depends(get_db)):
    """Confirm that a shipped order has been delivered. Transitions 'shipped' to 'delivered'.
    **When to use**: When the customer confirms receipt of the goods.
    **Returns**: The order with updated status='delivered'."""
    cached = check_idempotency(db, input_data.idempotency_key)
    if cached:
        data = json.loads(cached)
        return AgentResponse(data=data, current_state="delivered",
                             allowed_next_tools=get_order_allowed_tools("delivered"), error_guidance=None)
    order = db.query(models.Order).filter(models.Order.id == input_data.order_id).first()
    if not order:
        return AgentResponse(
            data=None, current_state="not_found", allowed_next_tools=["search_orders"],
            error_guidance=f"Order ID {input_data.order_id} not found.",
        )
    if order.status != "shipped":
        return AgentResponse(
            data=_order_data(order), current_state=order.status,
            allowed_next_tools=get_order_allowed_tools(order.status),
            error_guidance=f"Cannot confirm delivery: status is '{order.status}', must be 'shipped'.",
        )
    order.status = "delivered"
    db.commit()
    db.refresh(order)
    result = _order_data(order)
    save_idempotency(db, input_data.idempotency_key, "confirm_delivery", json.dumps(result))
    return AgentResponse(data=result, current_state="delivered",
                         allowed_next_tools=get_order_allowed_tools("delivered"), error_guidance=None)


@router.post("/cancel_order", response_model=AgentResponse)
def cancel_order(input_data: schemas.CancelOrderInput, db: Session = Depends(get_db)):
    """Cancel a pending order and restore product stock. Only 'pending' orders can be cancelled.
    For paid/shipped orders, use 'apply_refund' instead.
    **When to use**: When the user wants to cancel before payment.
    **Returns**: The cancelled order with status='cancelled'."""
    cached = check_idempotency(db, input_data.idempotency_key)
    if cached:
        data = json.loads(cached)
        return AgentResponse(data=data, current_state="cancelled",
                             allowed_next_tools=get_order_allowed_tools("cancelled"), error_guidance=None)
    order = db.query(models.Order).filter(models.Order.id == input_data.order_id).first()
    if not order:
        return AgentResponse(
            data=None, current_state="not_found", allowed_next_tools=["search_orders"],
            error_guidance=f"Order ID {input_data.order_id} not found.",
        )
    if order.status != "pending":
        guidance = f"Cannot cancel: status is '{order.status}', not 'pending'. "
        if order.status in ("paid", "shipped", "delivered"):
            guidance += "Since the order is already paid/shipped/delivered, use 'apply_refund' instead."
        return AgentResponse(
            data=_order_data(order), current_state=order.status,
            allowed_next_tools=get_order_allowed_tools(order.status), error_guidance=guidance,
        )
    for item in order.items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        if product:
            product.stock += item.quantity
    order.status = "cancelled"
    db.commit()
    db.refresh(order)
    result = _order_data(order)
    save_idempotency(db, input_data.idempotency_key, "cancel_order", json.dumps(result))
    return AgentResponse(data=result, current_state="cancelled",
                         allowed_next_tools=get_order_allowed_tools("cancelled"), error_guidance=None)
