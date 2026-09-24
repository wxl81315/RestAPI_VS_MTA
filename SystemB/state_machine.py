"""
State machine definitions for the MTA architecture.

Defines the allowed state transitions and the corresponding tools
that an Agent can invoke at each state. This is the core of P4 (Explicit State)
and P2 (Machine-Readable Affordances).
"""
from typing import Dict, List

# ============================================================
# Order State Machine
# ============================================================
# Valid order statuses: pending, paid, shipped, delivered,
#                       refund_pending, refunded, cancelled

ORDER_ALLOWED_TOOLS: Dict[str, List[str]] = {
    "pending": [
        "pay_order",
        "cancel_order",
        "update_order",
        "get_order_details",
    ],
    "paid": [
        "ship_order",
        "apply_refund",
        "get_order_details",
    ],
    "shipped": [
        "confirm_delivery",
        "apply_refund",
        "get_order_details",
    ],
    "delivered": [
        "apply_refund",
        "get_order_details",
    ],
    "refund_pending": [
        "approve_refund",
        "reject_refund",
        "get_order_details",
        "get_refund_details",
    ],
    "refunded": [
        "get_order_details",
    ],
    "cancelled": [
        "get_order_details",
    ],
}

ORDER_VALID_TRANSITIONS: Dict[str, List[str]] = {
    "pending":        ["paid", "cancelled"],
    "paid":           ["shipped", "refund_pending"],
    "shipped":        ["delivered", "refund_pending"],
    "delivered":      ["refund_pending"],
    "refund_pending": ["refunded", "paid", "shipped", "delivered"],
    "refunded":       [],
    "cancelled":      [],
}


def get_order_allowed_tools(status: str) -> List[str]:
    return ORDER_ALLOWED_TOOLS.get(status, ["search_orders"])


# ============================================================
# Refund State Machine
# ============================================================
# Valid refund statuses: pending, approved, rejected

REFUND_ALLOWED_TOOLS: Dict[str, List[str]] = {
    "pending": [
        "approve_refund",
        "reject_refund",
        "get_refund_details",
    ],
    "approved": [
        "get_refund_details",
        "get_order_details",
    ],
    "rejected": [
        "get_refund_details",
        "get_order_details",
        "apply_refund",
    ],
}


def get_refund_allowed_tools(status: str) -> List[str]:
    return REFUND_ALLOWED_TOOLS.get(status, ["search_refunds"])


# ============================================================
# Product "State" (products don't have states, but we keep consistent)
# ============================================================
PRODUCT_ALLOWED_TOOLS = [
    "search_products",
    "get_product_details",
    "create_product",
    "update_product",
    "delete_product",
]


def get_product_allowed_tools() -> List[str]:
    return PRODUCT_ALLOWED_TOOLS
