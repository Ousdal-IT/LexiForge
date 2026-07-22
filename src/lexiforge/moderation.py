import csv
import json
from pathlib import Path

from pydantic import ValidationError

from .errors import DataFormatError
from .models import CandidateStatus, CriterionValue, ReviewRecord
from .transitions import validate_transition

REVIEW_COLUMNS = (
    "id",
    "candidate_id",
    "reviewer_id",
    "decision",
    "reviewed_at",
    "criteria",
    "flags",
    "comment",
    "previous_status",
    "new_status",
)


def load_reviews(path: Path) -> list[ReviewRecord]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
                raise DataFormatError(f"{path}: invalid review columns")
            records = []
            for row_number, row in enumerate(reader, 2):
                values: dict[str, object] = dict(row)
                try:
                    try:
                        values["criteria"] = json.loads(row["criteria"])
                    except json.JSONDecodeError:
                        values["criteria"] = dict(
                            part.split("=", 1) for part in row["criteria"].split(";")
                        )
                    values["flags"] = json.loads(row["flags"])
                    review = ReviewRecord.model_validate(values)
                    validate_transition(review.previous_status, review.new_status)
                    records.append(review)
                except (json.JSONDecodeError, ValidationError, ValueError) as error:
                    raise DataFormatError(
                        f"{path}:{row_number}: invalid review: {error}"
                    ) from error
            return records
    except OSError as error:
        raise DataFormatError(f"cannot read {path}: {error}") from error


def required_criteria_resolved(review: ReviewRecord | None, required: list[str]) -> bool:
    if review is None:
        return False
    values = review.criteria.model_dump()
    return all(values[name] == CriterionValue.YES for name in required)


def latest_reviews(reviews: list[ReviewRecord]) -> dict[str, ReviewRecord]:
    result: dict[str, ReviewRecord] = {}
    for review in sorted(reviews, key=lambda item: (item.reviewed_at, item.id)):
        result[review.candidate_id] = review
    return result


def validate_review_history(
    reviews: list[ReviewRecord], candidates: dict[str, CandidateStatus]
) -> list[str]:
    errors = []
    latest = latest_reviews(reviews)
    for review in reviews:
        if review.candidate_id not in candidates:
            errors.append(f"orphaned review {review.id}")
    for candidate_id, review in latest.items():
        if candidate_id in candidates and candidates[candidate_id] != review.new_status:
            errors.append(f"candidate/review status mismatch for {candidate_id}")
    return sorted(errors)
