from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileChange:
    relative_path: str
    existed: bool
    before_sha256: str
    after_sha256: str
    content: bytes = b""


@dataclass(frozen=True, slots=True)
class ReleaseEligibilityImpact:
    language: str
    before: int
    after: int

    @property
    def delta(self) -> int:
        return self.after - self.before


@dataclass(frozen=True, slots=True)
class FieldChange:
    field: str
    before: str | None
    after: str | None


@dataclass(frozen=True, slots=True)
class StatusTransition:
    candidate_id: str
    before: str
    after: str


@dataclass(frozen=True, slots=True)
class ChangeSet:
    """Immutable, deterministic proposal produced by an editorial preview."""

    id: str
    repository_root: Path
    operation: str
    files: tuple[FileChange, ...]
    records_added: tuple[str, ...] = ()
    records_modified: tuple[str, ...] = ()
    records_superseded: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    validation_status: str = "valid"
    release_eligibility_impact: tuple[ReleaseEligibilityImpact, ...] = ()
    field_changes: tuple[FieldChange, ...] = ()
    status_transitions: tuple[StatusTransition, ...] = ()
    details: tuple[tuple[str, str], ...] = ()

    @property
    def affected_files(self) -> tuple[str, ...]:
        return tuple(change.relative_path for change in self.files)
