import csv
import io
from datetime import datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import yaml
from pydantic import ValidationError

from .atomic import atomic_write_text
from .constants import DEFAULT_DATA_ROOT
from .errors import DataFormatError, ValidationFailure
from .io import load_language_candidates
from .models import CandidateStatus, ReviewCriteria, ReviewDecision
from .profiles import load_policy
from .transitions import validate_transition

DECISION_STATUS = {
    ReviewDecision.APPROVE: CandidateStatus.APPROVED,
    ReviewDecision.REJECT: CandidateStatus.REJECTED,
    ReviewDecision.NEEDS_REVIEW: CandidateStatus.NEEDS_REVIEW,
    ReviewDecision.SUPERSEDE: CandidateStatus.SUPERSEDED,
    ReviewDecision.WITHDRAW: CandidateStatus.WITHDRAWN,
}


def load_criteria(path: Path | None) -> ReviewCriteria:
    values: object
    if path is None:
        values = {name: "unknown" for name in ReviewCriteria.model_fields}
    else:
        try:
            values = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as error:
            raise DataFormatError(f"cannot load review criteria {path}: {error}") from error
        if isinstance(values, dict):
            values = {
                key: "yes" if value is True else "no" if value is False else value
                for key, value in values.items()
            }
    try:
        return ReviewCriteria.model_validate(values)
    except ValidationError as error:
        raise DataFormatError(f"invalid review criteria: {error}") from error


def moderate_candidate(
    candidate_id: str,
    decision: ReviewDecision,
    reviewer: str,
    criteria: ReviewCriteria,
    comment: str,
    *,
    apply: bool = False,
    reviewed_at: str | None = None,
    data_root: Path = DEFAULT_DATA_ROOT,
) -> dict[str, object]:
    target = None
    language = ""
    for code_path in sorted((data_root / "languages").iterdir()):
        if not code_path.is_dir():
            continue
        for record in load_language_candidates(code_path.name, data_root):
            if record.candidate.id == candidate_id:
                target = record.candidate
                language = code_path.name
                break
    if target is None:
        raise ValidationFailure(f"candidate not found: {candidate_id}")
    new_status = DECISION_STATUS[decision]
    validate_transition(target.status, new_status)
    policy = load_policy(data_root)
    if decision == ReviewDecision.APPROVE:
        values = criteria.model_dump(mode="json")
        unresolved = [name for name in policy.required_review_criteria if values[name] != "yes"]
        if unresolved:
            raise ValidationFailure("approval requires resolved criteria: " + ", ".join(unresolved))
    report = {
        "schema_version": 1,
        "applied": apply,
        "candidate_id": candidate_id,
        "decision": decision.value,
        "previous_status": target.status.value,
        "new_status": new_status.value,
    }
    if not apply:
        return report
    if reviewed_at is None:
        raise ValidationFailure("--reviewed-at is required with --apply")
    try:
        datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValidationFailure("--reviewed-at must be ISO 8601") from error
    base = data_root / "languages" / language
    candidate_path = base / "candidates.csv"
    with candidate_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    for row in rows:
        if row["id"] == candidate_id:
            row["status"] = new_status.value
            row["reviewed_at"] = reviewed_at
    candidate_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(candidate_buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    criteria_text = ";".join(
        f"{name}={value}" for name, value in criteria.model_dump(mode="json").items()
    )
    review_path = base / "reviews.csv"
    review_content = review_path.read_text(encoding="utf-8")
    review_buffer = io.StringIO(newline="")
    review_buffer.write(review_content)
    review_id = str(
        uuid5(NAMESPACE_URL, f"lexiforge:review:{candidate_id}:{reviewed_at}:{decision.value}")
    )
    csv.writer(review_buffer, lineterminator="\n").writerow(
        [
            review_id,
            candidate_id,
            reviewer,
            decision.value,
            reviewed_at,
            criteria_text,
            "[]",
            comment,
            target.status.value,
            new_status.value,
        ]
    )
    atomic_write_text(candidate_path, candidate_buffer.getvalue())
    atomic_write_text(review_path, review_buffer.getvalue())
    return report
