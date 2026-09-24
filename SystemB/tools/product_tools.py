"""
Product Tools — MTA tool endpoints for product management.

Each tool returns AgentResponse with:
  - current_state: explicit state of the entity
  - allowed_next_tools: what the Agent can call next
  - error_guidance: natural-language recovery instructions on errors

This module embeds business-rule traps (LOCKED status, duplicate names,
pagination cursors, negative prices) and converts them into ACTIONABLE
guidance for the Agent — instead of cold HTTP errors.
"""
from __future__ import annotations
import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import models
import schemas
from schemas import AgentResponse
from database import get_db
from state_machine import get_product_allowed_tools
from idempotency import check_idempotency, save_idempotency

router = APIRouter(prefix="/tools", tags=["Product Tools"])


# ============================================================
#  search_products
# ============================================================
@router.post("/search_products", response_model=AgentResponse)
def search_products(input_data: schemas.SearchProductsInput, db: Session = Depends(get_db)):
    """Search and list products in the catalog by optional keyword.

    Returns a paginated list. If more records exist beyond the current page,
    error_guidance tells the Agent how to fetch them.
    """
    q = db.query(models.Product)
    if input_data.keyword:
        q = q.filter(models.Product.name.contains(input_data.keyword))

    total_count = q.count()
    products = q.offset(input_data.skip).limit(input_data.limit).all()
    products_data = [schemas.ProductData.model_validate(p).model_dump(mode="json")
                     for p in products]

    has_more = (input_data.skip + len(products_data)) < total_count
    next_skip = input_data.skip + input_data.limit

    guidance = None
    if has_more:
        guidance = (
            f"More records exist. This page returned {len(products_data)} items "
            f"out of {total_count} total. To see all matching products, call "
            f"'search_products' again with skip={next_skip} and the same keyword."
        )

    return AgentResponse(
        data={
            "products": products_data,
            "total_returned": len(products_data),
            "total_count": total_count,
            "skip": input_data.skip,
            "limit": input_data.limit,
            "has_more": has_more,
            "next_skip": next_skip if has_more else None,
        },
        current_state="list_result",
        allowed_next_tools=["get_product_details", "create_product",
                            "update_product", "search_products"],
        error_guidance=guidance,
    )


# ============================================================
#  get_product_details
# ============================================================
@router.post("/get_product_details", response_model=AgentResponse)
def get_product_details(input_data: schemas.GetProductDetailsInput,
                        db: Session = Depends(get_db)):
    """Get detailed information about a single product by its ID."""
    product = db.query(models.Product).filter(
        models.Product.id == input_data.product_id
    ).first()

    if not product:
        return AgentResponse(
            data=None,
            current_state="not_found",
            allowed_next_tools=["search_products", "create_product"],
            error_guidance=(
                f"Product with ID {input_data.product_id} does not exist. "
                f"You can: (1) Use 'search_products' to find valid IDs, or "
                f"(2) Use 'create_product' to add it as a new item."
            ),
        )

    data = schemas.ProductData.model_validate(product).model_dump(mode="json")

    # ── LOCKED early-warning: force the Agent to check for user authorization ──
    if product.status == "LOCKED":
        return AgentResponse(
            data=data,
            current_state="LOCKED",
            allowed_next_tools=["get_product_details", "update_product"],
            error_guidance=(
                f"Product {product.id} ('{product.name}') is in LOCKED status. "
                f"LOCKED products are intentionally protected (legal hold, audit lock, etc.). "
                f"Re-read the USER'S ORIGINAL REQUEST and decide:\n"
                f"\n=== CASE 1: User ALREADY authorized unlocking ===\n"
                f"If the original request contains explicit authorization such as "
                f"'我授权你...先解除限制', 'unlock if needed', 'remove restrictions', "
                f"'delete it anyway', or any wording allowing you to bypass business "
                f"restrictions: AUTHORIZATION IS ALREADY GIVEN. "
                f"DO NOT ask the user again. DO NOT write a final answer that merely "
                f"announces your plan. Instead, IMMEDIATELY in this same turn: "
                f"(1) call update_product(product_id, status='NORMAL', idempotency_key=...), "
                f"(2) then call delete_product(product_id, idempotency_key=...). "
                f"Only AFTER both tools succeed, write your final answer summarizing the "
                f"two completed actions.\n"
                f"\n=== CASE 2: User has NOT authorized unlocking ===\n"
                f"If the original request only says e.g. 'delete this product' without "
                f"any wording about removing restrictions or unlocking: DO NOT unlock on "
                f"your own. STOP HERE. In your final answer inform the user the product "
                f"is LOCKED and deletion is REFUSED, and ASK for explicit confirmation."
            ),
        )

    return AgentResponse(
        data=data,
        current_state=product.status,  # NORMAL
        allowed_next_tools=get_product_allowed_tools(),
        error_guidance=None,
    )


# ============================================================
#  create_product
# ============================================================
@router.post("/create_product", response_model=AgentResponse)
def create_product(input_data: schemas.CreateProductInput, db: Session = Depends(get_db)):
    """Create a new product in the catalog.

    Validates price > 0 and warns about duplicate names before committing.
    """
    # ── Idempotency cache ──
    cached = check_idempotency(db, input_data.idempotency_key)
    if cached:
        return AgentResponse(
            data=json.loads(cached),
            current_state="NORMAL",
            allowed_next_tools=get_product_allowed_tools(),
            error_guidance=None,
        )

    # ── Validation: price must be > 0 ──
    if input_data.price <= 0:
        return AgentResponse(
            data=None,
            current_state="validation_error",
            allowed_next_tools=["create_product"],
            error_guidance=(
                f"The 'price' field is {input_data.price} but must be strictly greater than 0. "
                f"Correct the price and retry with a NEW idempotency_key. "
                f"If the user provided a negative number, ask them to confirm a positive price."
            ),
        )

    # ── Validation: stock must be >= 0 ──
    if input_data.stock < 0:
        return AgentResponse(
            data=None,
            current_state="validation_error",
            allowed_next_tools=["create_product"],
            error_guidance=(
                f"The 'stock' field is {input_data.stock} but must be >= 0. "
                f"Correct it and retry with a NEW idempotency_key."
            ),
        )

    # ── Duplicate name detection ──
    existing = db.query(models.Product).filter(
        models.Product.name == input_data.name
    ).all()
    if existing:
        existing_ids = [p.id for p in existing]
        return AgentResponse(
            data={"existing_product_ids": existing_ids,
                  "existing_count": len(existing)},
            current_state="duplicate_name",
            allowed_next_tools=["get_product_details", "create_product",
                                "update_product"],
            error_guidance=(
                f"A product named '{input_data.name}' already exists "
                f"(IDs: {existing_ids}). Confirm with the user whether to: "
                f"(1) update the existing product via 'update_product', or "
                f"(2) create a duplicate anyway by adding a unique suffix to the name "
                f"(e.g. '{input_data.name} v2') and retry with a NEW idempotency_key."
            ),
        )

    # ── Commit ──
    product = models.Product(
        name=input_data.name,
        description=input_data.description or "",
        price=input_data.price,
        stock=input_data.stock,
        status="NORMAL",
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    result_data = schemas.ProductData.model_validate(product).model_dump(mode="json")
    save_idempotency(db, input_data.idempotency_key, "create_product",
                     json.dumps(result_data))
    return AgentResponse(
        data=result_data,
        current_state="NORMAL",
        allowed_next_tools=get_product_allowed_tools(),
        error_guidance=None,
    )



# ============================================================
#  update_product
# ============================================================
@router.post("/update_product", response_model=AgentResponse)
def update_product(input_data: schemas.UpdateProductInput, db: Session = Depends(get_db)):
    """Partially update an existing product.

    PARTIAL UPDATE: Only fields the Agent EXPLICITLY sets in the JSON payload
    will be applied. Fields omitted from the payload are left untouched.

    NOTE: If the Agent sends e.g. {'name': ''} or {'price': 0}, the system
    treats this as a destructive write attempt and returns error_guidance
    instructing the Agent to OMIT those fields entirely.
    """
    cached = check_idempotency(db, input_data.idempotency_key)
    if cached:
        return AgentResponse(
            data=json.loads(cached),
            current_state="NORMAL",
            allowed_next_tools=get_product_allowed_tools(),
            error_guidance=None,
        )

    product = db.query(models.Product).filter(
        models.Product.id == input_data.product_id
    ).first()
    if not product:
        return AgentResponse(
            data=None,
            current_state="not_found",
            allowed_next_tools=["search_products"],
            error_guidance=(
                f"Product with ID {input_data.product_id} not found. "
                f"Use 'search_products' first to find a valid ID."
            ),
        )

    # ── Detect "destructive empty values" ──
    # Only consider fields the user explicitly set (exclude_unset).
    explicit = input_data.model_dump(
        exclude_unset=True,
        exclude={"product_id", "idempotency_key"},
    )
    destructive = []
    if "name" in explicit and (explicit["name"] is None or explicit["name"] == ""):
        destructive.append("name")
    if "price" in explicit and explicit["price"] is not None and explicit["price"] <= 0:
        destructive.append("price")
    if "stock" in explicit and explicit["stock"] is not None and explicit["stock"] < 0:
        destructive.append("stock")

    if destructive:
        return AgentResponse(
            data={"current_product": schemas.ProductData.model_validate(product)
                  .model_dump(mode="json"),
                  "destructive_fields": destructive},
            current_state="validation_error",
            allowed_next_tools=["update_product", "get_product_details"],
            error_guidance=(
                f"You attempted to set field(s) {destructive} to empty/zero/negative "
                f"value(s) on product {input_data.product_id}. This is not a partial-update "
                f"intent. To keep these fields unchanged, OMIT them entirely from your "
                f"next call. Only include fields you actually want to modify. Retry with a "
                f"NEW idempotency_key."
            ),
        )

    # ── Validate status enum if provided ──
    if "status" in explicit and explicit["status"] not in ("NORMAL", "LOCKED"):
        return AgentResponse(
            data=None,
            current_state="validation_error",
            allowed_next_tools=["update_product"],
            error_guidance=(
                f"Invalid status '{explicit['status']}'. Allowed values are 'NORMAL' or 'LOCKED'."
            ),
        )

    # ── Apply changes ──
    for key, value in explicit.items():
        if value is not None:
            setattr(product, key, value)
    db.commit()
    db.refresh(product)

    result_data = schemas.ProductData.model_validate(product).model_dump(mode="json")
    save_idempotency(db, input_data.idempotency_key, "update_product",
                     json.dumps(result_data))
    return AgentResponse(
        data=result_data,
        current_state=product.status,
        allowed_next_tools=get_product_allowed_tools(),
        error_guidance=None,
    )


# ============================================================
#  delete_product
# ============================================================
@router.post("/delete_product", response_model=AgentResponse)
def delete_product(input_data: schemas.DeleteProductInput, db: Session = Depends(get_db)):
    """Permanently delete a product.

    Business rule: products in 'LOCKED' status cannot be deleted. The Agent
    must first transition them to 'NORMAL' via 'update_product'.
    """
    cached = check_idempotency(db, input_data.idempotency_key)
    if cached:
        return AgentResponse(
            data=json.loads(cached),
            current_state="deleted",
            allowed_next_tools=["search_products", "create_product"],
            error_guidance=None,
        )

    product = db.query(models.Product).filter(
        models.Product.id == input_data.product_id
    ).first()
    if not product:
        return AgentResponse(
            data=None,
            current_state="not_found",
            allowed_next_tools=["search_products"],
            error_guidance=(
                f"Product ID {input_data.product_id} not found. It may already be deleted."
            ),
        )

    # ── LOCKED business rule trap ──
    if product.status == "LOCKED":
        return AgentResponse(
            data=schemas.ProductData.model_validate(product).model_dump(mode="json"),
            current_state="LOCKED",
            allowed_next_tools=["get_product_details", "update_product"],
            error_guidance=(
                f"Product {input_data.product_id} ('{product.name}') is in LOCKED status. "
                f"Deletion is REFUSED on a locked product. "
                f"BEFORE doing anything else, CHECK THE USER'S ORIGINAL REQUEST: "
                f"\n- If the user EXPLICITLY authorized unlocking / removing business "
                f"restrictions / 'delete it anyway' / similar wording, you MAY proceed: "
                f"call update_product(status='NORMAL'), then delete_product again with a "
                f"NEW idempotency_key. "
                f"\n- If the user did NOT explicitly authorize unlocking, DO NOT unlock on "
                f"your own. STOP HERE, inform the user in your final answer that the "
                f"product is LOCKED and deletion was REFUSED, and ask for explicit "
                f"confirmation to unlock."
            ),
        )

    result_data = schemas.ProductData.model_validate(product).model_dump(mode="json")
    db.delete(product)
    db.commit()
    save_idempotency(db, input_data.idempotency_key, "delete_product",
                     json.dumps(result_data))
    return AgentResponse(
        data=result_data,
        current_state="deleted",
        allowed_next_tools=["search_products", "create_product"],
        error_guidance=None,
    )
