"""DrugCLIP AppError signature tests."""
import pytest
from fastapi import status

from app.core.errors import AppError


def test_app_error_requires_message_and_code():
    err = AppError(
        message="DrugCLIP service unreachable: connection refused",
        code="DRUGCLIP_UNAVAILABLE",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )
    assert err.detail == "DrugCLIP service unreachable: connection refused"
    assert err.code == "DRUGCLIP_UNAVAILABLE"
    assert err.status_code == 503


def test_app_error_rejects_reason_kwarg():
    with pytest.raises(TypeError):
        AppError(reason="bad", status_code=500)
