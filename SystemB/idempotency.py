"""
Idempotency Key management (P6: Immutability and Safe Execution).

Ensures that if an Agent retries a tool call with the same idempotency_key,
the system returns the cached result instead of executing the operation again.
"""
import json
from sqlalchemy.orm import Session
from typing import Optional

from models import IdempotencyKey


def check_idempotency(db: Session, key: str) -> Optional[str]:
    """
    Check if an idempotency key has already been used.
    Returns the cached result_snapshot if found, None otherwise.
    """
    record = db.query(IdempotencyKey).filter(IdempotencyKey.key == key).first()
    if record:
        return record.result_snapshot
    return None


def save_idempotency(db: Session, key: str, tool_name: str, result_snapshot: str):
    """
    Save an idempotency key after a successful operation.
    """
    record = IdempotencyKey(
        key=key,
        tool_name=tool_name,
        result_snapshot=result_snapshot,
    )
    db.add(record)
    db.commit()
