import logging
import uuid

import pytest

from app.core.audit import log_audit_event


def test_log_audit_event(caplog: pytest.LogCaptureFixture) -> None:
    actor_id = uuid.uuid4()
    target_id = uuid.uuid4()

    with caplog.at_level(logging.INFO, logger="jepret.audit"):
        log_audit_event(
            "test.action",
            actor_user_id=actor_id,
            target_id=target_id,
            metadata={"detail": "sample"},
        )

    assert len(caplog.records) > 0
    record = caplog.records[0]
    assert record.getMessage() == "audit_event"
    assert getattr(record, "audit", {}).get("event_type") == "test.action"
    assert getattr(record, "audit", {}).get("actor_user_id") == str(actor_id)
    assert getattr(record, "audit", {}).get("target_id") == str(target_id)
