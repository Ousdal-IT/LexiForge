"""Typed models for derived index metadata and query results."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..models import WordCandidate


@dataclass(frozen=True, slots=True)
class IndexMetadata:
    format_version: int
    compatibility_version: str
    schema_version: int
    repository_identity: str
    files: dict[str, str]
    profile_fingerprints: dict[str, str]
    blocklist_fingerprints: dict[str, str]
    record_counts: dict[str, int]
    capabilities: tuple[str, ...]
    builder_version: str
    completed: bool
    created_at: str | None = None

    def as_dict(self, *, include_diagnostic_time: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "format_version": self.format_version,
            "compatibility_version": self.compatibility_version,
            "schema_version": self.schema_version,
            "repository_identity": self.repository_identity,
            "files": dict(sorted(self.files.items())),
            "profile_fingerprints": dict(sorted(self.profile_fingerprints.items())),
            "blocklist_fingerprints": dict(sorted(self.blocklist_fingerprints.items())),
            "record_counts": dict(sorted(self.record_counts.items())),
            "capabilities": list(self.capabilities),
            "builder_version": self.builder_version,
            "completed": self.completed,
        }
        if include_diagnostic_time and self.created_at is not None:
            result["created_at"] = self.created_at
        return result

    def to_json(self, *, include_diagnostic_time: bool = True) -> str:
        return (
            json.dumps(
                self.as_dict(include_diagnostic_time=include_diagnostic_time),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )


@dataclass(frozen=True, slots=True)
class IndexedCandidate:
    candidate: WordCandidate
    normalized_word: str
    release_eligible: bool
    eligibility_reasons: tuple[str, ...]
    blocklist_match: bool


@dataclass(frozen=True, slots=True)
class IndexStatus:
    path: str
    present: bool
    valid: bool
    state: str
    metadata: IndexMetadata | None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class IndexQueryPage:
    items: tuple[IndexedCandidate, ...]
    total: int
    offset: int
    limit: int


def parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def parse_json_record(value: str, model: type[Any]) -> Any:
    return model.model_validate_json(value)


__all__ = ["IndexMetadata", "IndexedCandidate", "IndexQueryPage", "IndexStatus"]
