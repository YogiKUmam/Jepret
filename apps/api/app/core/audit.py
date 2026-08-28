import logging
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("jepret.audit")


def log_audit_event(
    event_type: str,
    *,
    actor_user_id: uuid.UUID | None = None,
    target_id: uuid.UUID | str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record an immutable, structured governance audit entry."""
    payload = {
        "event_type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "target_id": str(target_id) if target_id else None,
        "metadata": metadata or {},
    }
    logger.info("audit_event", extra={"audit": payload})
