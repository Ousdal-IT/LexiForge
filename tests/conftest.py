from pathlib import Path

import pytest

from lexiforge.constants import DEFAULT_DATA_ROOT
from lexiforge.io import load_language_candidates
from lexiforge.models import CandidateRecord, WordCandidate
from lexiforge.profiles import load_categories, load_language_profile


@pytest.fixture
def nb_profile():
    return load_language_profile("nb")


@pytest.fixture
def categories():
    return {item.id for item in load_categories().categories}


@pytest.fixture
def nb_records():
    return load_language_candidates("nb")


def record(**changes: object) -> CandidateRecord:
    values: dict[str, object] = {
        "id": "90000000-0000-4000-8000-000000000001",
        "language": "nb",
        "word": "skog",
        "status": "approved",
        "category": "nature",
        "source_type": "fixture",
        "score": 50,
        "license_eligible": True,
    }
    values.update(changes)
    return CandidateRecord(
        candidate=WordCandidate.model_validate(values), file="fixture.csv", row=2
    )


@pytest.fixture
def data_root() -> Path:
    return DEFAULT_DATA_ROOT
