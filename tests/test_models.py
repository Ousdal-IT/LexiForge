from datetime import UTC

import pytest
from pydantic import ValidationError

from lexiforge.models import WordCandidate


def valid_values() -> dict[str, object]:
    return {
        "id": "90000000-0000-4000-8000-000000000001",
        "language": "en",
        "word": "apple",
        "status": "approved",
        "source_type": "fixture",
    }


def test_valid_candidate() -> None:
    item = WordCandidate.model_validate({**valid_values(), "submitted_at": "2025-01-02T03:04:05Z"})
    assert item.submitted_at and item.submitted_at.tzinfo == UTC


@pytest.mark.parametrize(
    "field,value",
    [
        ("language", "INVALID"),
        ("status", "maybe"),
        ("source_type", "robot"),
        ("score", 101),
        ("submitted_at", "yesterday"),
    ],
)
def test_invalid_fields(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        WordCandidate.model_validate({**valid_values(), field: value})


def test_unknown_field() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        WordCandidate.model_validate({**valid_values(), "mystery": True})
