import csv
from pathlib import Path

from pydantic import ValidationError

from .errors import DataFormatError
from .models import ProvenanceRecord

PROVENANCE_COLUMNS = (
    "id",
    "candidate_id",
    "source_kind",
    "source_reference",
    "contributor_assertion",
    "license_basis",
    "independently_contributed",
    "bulk_source",
    "created_at",
    "notes",
)


def load_provenance(path: Path) -> list[ProvenanceRecord]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != PROVENANCE_COLUMNS:
                raise DataFormatError(f"{path}: invalid provenance columns")
            records = []
            for row_number, row in enumerate(reader, 2):
                values: dict[str, object] = dict(row)
                if not values["source_reference"]:
                    values["source_reference"] = None
                if not values["created_at"]:
                    values["created_at"] = None
                try:
                    records.append(ProvenanceRecord.model_validate(values))
                except ValidationError as error:
                    raise DataFormatError(
                        f"{path}:{row_number}: invalid provenance: {error}"
                    ) from error
            return records
    except OSError as error:
        raise DataFormatError(f"cannot read {path}: {error}") from error


def validate_provenance_links(
    records: list[ProvenanceRecord], candidate_ids: set[str]
) -> list[str]:
    return sorted(record.id for record in records if record.candidate_id not in candidate_ids)
