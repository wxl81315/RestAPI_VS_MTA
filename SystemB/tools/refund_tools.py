"""
Refund Tools — MTA tool endpoints for refund/after-sales management.
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
from state_machine import get_order_allowed_tools, get_refund_allowed_tools
from idempotency import check_idempotency, save_idempotency

router = APIRouter(prefix="/tools", tags=["Refund Tools"])


def _refund_data(refund) -> dict:
    return schemas.RefundData.model_validate(refund).model_dump(mode="json")


@router.post("/apply_refund", response_model=AgentResponse)
def apply_refund(input_data: schemas.ApplyRefundInput, db: Session = Depends(get_db)):
    """Apply for a refund on an existing order.
    The order must be in 'paid', 'shipped', or 'delivered' status.
    The refund amount must not exceed the order's total_amount.
    DO NOT guess the refund reason — ask the user if they haven't provided one.
    **When to use**: When a customer requests a refund after payment.
    **Returns**: The created refund record with status='pending', plus the order's updated state."""
    cached = check_idempotency(db, input_data.idempotency_key)
    if cached:
        data = json.loads(cached)
        return AgentResponse(data=data, current_state="refund_pending",
                             allowed_next_tools=get_order_allowed_tools("refund_pending"), error_guidance=None)

    order = db.query(models.Order).filter(models.Order.id == input_data.order_id).first()
    if not order:
        return AgentResponse(
            data=None, current_state="not_found", allowed_next_tools=["search_orders"],
            error_guidance=f"Order ID {input_data.order_id} not found. "
                          f"Use 'search_orders' to find the correct order ID.",
        )

    allowed_statuses = ("paid", "shipped", "delivered")
    if order.status not in allowed_statuses:
        if order.status == "pending":
            guidance = ("Cannot refund a 'pending' order because payment hasn't been made yet. "
                       "Use 'cancel_order' to cancel unpaid orders instead.")
        elif order.status == "refund_pending":
            guidance = ("A refund is already pending for this order. "
                       "Use 'get_refund_details' or 'search_refunds' to check existing refund status. "
                       "Use 'approve_refund' or 'reject_refund' to process it.")
        elif order.status == "refunded":
            guidance = "This order has already been refunded. No further refund action is possible."
        elif order.status == "cancelled":
            guidance = "This order was cancelled. Cancelled orders cannot be refunded."
        else:
            guidance = f"Order status '{order.status}' does not allow refunds."
        return AgentResponse(
            data=schemas.OrderData.model_validate(order).model_dump(mode="json"),
            current_state=order.status,
            allowed_next_tools=get_order_allowed_tools(order.status),
            error_guidance=guidance,
        )

    if input_data.amount <= 0:
        return AgentResponse(
            data=None, current_state="validation_error",
            allowed_next_tools=["apply_refund", "get_order_details"],
            error_guidance="Refund amount must be greater than 0. Please correct and retry.",
        )

    if input_data.amount > order.total_amount:
        return AgentResponse(
            data={"order_total_amount": order.total_amount, "requested_amount": input_data.amount},
            current_state=order.status,
            allowed_next_tools=["apply_refund", "get_order_details"],
            error_guidance=f"Refund amount ({input_data.amount}) exceeds order total ({order.total_amount}). "
                          f"The refund amount must be <= {order.total_amount}. "
                          f"Ask the user for the correct refund amount.",
        )

    refund_no = "R" + uuid.uuid4().hex[:7].upper()
    order.status = "refund_pending"
    refund = models.Refund(refund_no=refund_no, order_id=input_data.order_id,
                           reason=input_data.reason, amount=input_data.amount, status="pending")
    db.add(refund)
    db.commit()
    db.refresh(refund)

    result = {"refund": _refund_data(refund),
              "order_status": "refund_pending", "order_id": order.id}
    save_idempotency(db, input_data.idempotency_key, "apply_refund", json.dumps(result))
    return AgentResponse(
        data=result, current_state="refund_pending",
        allowed_next_tools=get_order_allowed_tools("refund_pending"), error_guidance=None,
    )


@router.post("/search_refunds", response_model=AgentResponse)
def search_refunds(input_data: schemas.SearchRefundsInput, db: Session = Depends(get_db)):
    """Search and list refund records with optional filters.
    **When to use**: To find refunds by order_id or status, or browse all refund requests.
    **Returns**: A list of refund objects with id, refund_no, order_id, reason, amount, status."""
    q = db.query(models.Refund)
    if input_data.order_id:
        q = q.filter(models.Refund.order_id == input_data.order_id)
    if input_data.status:
        valid = ["pending", "approved", "rejected"]
        if input_data.status not in valid:
            return AgentResponse(
                data=None, current_state="validation_error",
                allowed_next_tools=["search_refunds"],
                error_guidance=f"Invalid refund status '{input_data.status}'. Valid: {', '.join(valid)}.",
            )
        q = q.filter(models.Refund.status == input_data.status)
    refunds = q.order_by(models.Refund.id.desc()).offset(input_data.skip).limit(input_data.limit).all()
    data = [_refund_data(r) for r in refunds]
    return AgentResponse(
        data={"refunds": data, "total_returned": len(data)},
        current_state="list_result",
        allowed_next_tools=["get_refund_details", "approve_refund", "reject_refund", "search_refunds"],
        error_guidance=None,
    )


@router.post("/get_refund_details", response_model=AgentResponse)
def get_refund_details(input_data: schemas.GetRefundDetailsInput, db: Session = Depends(get_db)):
    """Get full details of a specific refund record.
    **When to use**: Before approving or rejecting a refund to verify its current status.
    **Returns**: Complete refund object with status, reason, amount, and timestamps."""
    refund = db.query(models.Refund).filter(models.Refund.id == input_data.refund_id).first()
    if not refund:
        return AgentResponse(
            data=None, current_state="not_found", allowed_next_tools=["search_refunds"],
            error_guidance=f"Refund ID {input_data.refund_id} not found. Use 'search_refunds' to find valid IDs.",
        )
    return AgentResponse(
        data=_refund_data(refund), current_state=refund.status,
        allowed_next_tools=get_refund_allowed_tools(refund.status), error_guidance=None,
    )


@router.post("/approve_refund", response_model=AgentResponse)
def approve_refund(input_data: schemas.ApproveRefundInput, db: Session = Depends(get_db)):
    """Approve a pending refund request. This will:
    1. Set refund status to 'approved'
    2. Set order status to 'refunded'
    3. Restore product stock for all order items
    **When to use**: When an admin decides to approve the refund.
    **Returns**: The approved refund record and updated order status."""
    cached = check_idempotency(db, input_data.idempotency_key)
    if cached:
        data = json.loads(cached)
        return AgentResponse(data=data, current_state="approved",
                             allowed_next_tools=get_refund_allowed_tools("approved"), error_guidance=None)

    refund = db.query(models.Refund).filter(models.Refund.id == input_data.refund_id).first()
    if not refund:
        return AgentResponse(
            data=None, current_state="not_found", allowed_next_tools=["search_refunds"],
            error_guidance=f"Refund ID {input_data.refund_id} not found.",
        )

    if refund.status != "pending":
        return AgentResponse(
            data=_refund_data(refund), current_state=refund.status,
            allowed_next_tools=get_refund_allowed_tools(refund.status),
            error_guidance=f"Cannot approve: refund status is '{refund.status}', not 'pending'. "
                          f"{'It was already approved.' if refund.status == 'approved' else 'It was rejected.'}",
        )

    refund.status = "approved"
    order = db.query(models.Order).filter(models.Order.id == refund.order_id).first()
    order.status = "refunded"
    for item in order.items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        if product:
            product.stock += item.quantity
    db.commit()
    db.refresh(refund)

    result = {"refund": _refund_data(refund), "order_status": "refunded", "order_id": order.id}
    save_idempotency(db, input_data.idempotency_key, "approve_refund", json.dumps(result))
    return AgentResponse(
        data=result, current_state="approved",
        allowed_next_tools=get_refund_allowed_tools("approved"), error_guidance=None,
    )


@router.post("/reject_refund", response_model=AgentResponse)
def reject_refund(input_data: schemas.RejectRefundInput, db: Session = Depends(get_db)):
    """Reject a pending refund request. The order will revert to 'paid' status.
    **When to use**: When an admin decides to reject the refund.
    **Returns**: The rejected refund record and the order's restored status."""
    cached = check_idempotency(db, input_data.idempotency_key)
    if cached:
        data = json.loads(cached)
        return AgentResponse(data=data, current_state="rejected",
                             allowed_next_tools=get_refund_allowed_tools("rejected"), error_guidance=None)

    refund = db.query(models.Refund).filter(models.Refund.id == input_data.refund_id).first()
    if not refund:
        return AgentResponse(
            data=None, current_state="not_found", allowed_next_tools=["search_refunds"],
            error_guidance=f"Refund ID {input_data.refund_id} not found.",
        )

    if refund.status != "pending":
        return AgentResponse(
            data=_refund_data(refund), current_state=refund.status,
            allowed_next_tools=get_refund_allowed_tools(refund.status),
            error_guidance=f"Cannot reject: refund status is '{refund.status}', not 'pending'.",
        )

    refund.status = "rejected"
    order = db.query(models.Order).filter(models.Order.id == refund.order_id).first()
    order.status = "paid"
    db.commit()
    db.refresh(refund)

    result = {"refund": _refund_data(refund), "order_status": "paid", "order_id": order.id}
    save_idempotency(db, input_data.idempotency_key, "reject_refund", json.dumps(result))
    return AgentResponse(
        data=result, current_state="rejected",
        allowed_next_tools=get_refund_allowed_tools("rejected"), error_guidance=None,
    )
