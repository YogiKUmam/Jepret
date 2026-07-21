import uuid
from datetime import UTC, datetime

import pytest

from app.core.errors import DomainError
from app.services.creators import decode_cursor, encode_cursor


def test_cursor_roundtrip() -> None:
    reviewed_at = datetime(2026, 7, 21, 10, 30, tzinfo=UTC)
    creator_id = uuid.uuid4()
    encoded = encode_cursor(reviewed_at, creator_id)
    assert decode_cursor(encoded) == (reviewed_at, creator_id)


def test_cursor_is_opaque_base64url() -> None:
    encoded = encode_cursor(datetime(2026, 7, 21, tzinfo=UTC), uuid.uuid4())
    assert "|" not in encoded
    assert " " not in encoded


@pytest.mark.parametrize("bad", ["", "not-base64!!", "aGFsbw==", "aGFsbHx4"])
def test_decode_rejects_invalid_cursor(bad: str) -> None:
    with pytest.raises(DomainError) as exc_info:
        decode_cursor(bad)
    assert exc_info.value.code == "INVALID_CURSOR"
    assert exc_info.value.status_code == 422
