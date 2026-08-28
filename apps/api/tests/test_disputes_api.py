import pytest
from pydantic import ValidationError

from app.api.dispute_schemas import CreateDisputeRequest, ResolveDisputeRequest
from app.main import create_app


def test_dispute_request_validation() -> None:
    req = CreateDisputeRequest(
        reason_category="not_delivered",
        description="Kreator tidak hadir dan tidak menyerahkan foto.",
    )
    assert req.reason_category == "not_delivered"

    with pytest.raises(ValidationError):
        CreateDisputeRequest(
            reason_category="invalid_category",  # type: ignore[arg-type]
            description="Deskripsi pendek",
        )

    with pytest.raises(ValidationError):
        CreateDisputeRequest(
            reason_category="quality_issue",
            description="Pendek",  # less than 10 chars
        )

    resolve_req = ResolveDisputeRequest(
        resolution="resolved_client",
        resolution_notes="Bukti menunjukkan kreator tidak datang ke lokasi.",
    )
    assert resolve_req.resolution == "resolved_client"

    with pytest.raises(ValidationError):
        ResolveDisputeRequest(
            resolution="invalid_resolution",  # type: ignore[arg-type]
            resolution_notes="Catatan",
        )


def test_disputes_route_registration() -> None:
    app = create_app()
    paths = app.openapi()["paths"]
    assert "/api/v1/bookings/{booking_id}/disputes" in paths
    assert "/api/v1/bookings/{booking_id}/dispute" in paths
    assert "/api/v1/admin/overview" in paths
    assert "/api/v1/admin/disputes" in paths
    assert "/api/v1/admin/disputes/{dispute_id}/resolve" in paths
