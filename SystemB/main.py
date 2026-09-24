"""
System B — MTA Architecture E-commerce API.

This API exposes all endpoints as Agent-callable "tools" under /tools/*,
following the Model-Tool-Agent (MTA) architecture principles:
  P1: Self-Descriptive — detailed docstrings and Pydantic schemas
  P2: Machine-Readable — structured AgentResponse with allowed_next_tools
  P3: Fault Tolerance — error_guidance instead of HTTP exceptions
  P4: Explicit State — current_state in every response
  P5: Composability — tools chain via allowed_next_tools
  P6: Immutability — idempotency keys on all mutations

Runs on port 8001 (System A uses 8000). Shares the same SQLite database.
"""
from fastapi import FastAPI
from database import engine, SessionLocal
from models import Base, Product
from tools import product_tools, order_tools, refund_tools

app = FastAPI(
    title="E-commerce MTA API (System B)",
    version="1.0.0",
    description="MTA-architecture e-commerce backend. All endpoints return AgentResponse "
                "with explicit state, allowed_next_tools, and error_guidance.",
)

app.include_router(product_tools.router)
app.include_router(order_tools.router)
app.include_router(refund_tools.router)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    """Health check — confirms System B (MTA) is running."""
    return {
        "system": "B",
        "architecture": "MTA (Model-Tool-Agent)",
        "status": "ok",
        "available_tools": [
            "search_products", "get_product_details", "create_product",
            "update_product", "delete_product",
            "create_order", "search_orders", "get_order_details",
            "update_order", "pay_order", "ship_order",
            "confirm_delivery", "cancel_order",
            "apply_refund", "search_refunds", "get_refund_details",
            "approve_refund", "reject_refund",
        ],
    }
