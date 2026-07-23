"""Typed, backend-neutral read API over the disposable SQLite index."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import CandidateStatus, ProvenanceRecord, ReviewRecord, WordCandidate
from ..repository import DATASET_SCHEMA_VERSION, DatasetRepository
from .errors import (
    IndexCompatibilityError,
    IndexCorruptionError,
    IndexNotFoundError,
    IndexStaleError,
    RepositoryIndexError,
)
from .metadata import (
    FORMAT_VERSION,
    compatibility_fingerprint,
    file_fingerprints,
    repository_identity,
)
from .model import IndexedCandidate, IndexMetadata, IndexQueryPage, IndexStatus
from .storage import index_path, sqlite_integrity_errors


class RepositoryIndex:
    """Read-only index handle. Canonical files remain authoritative."""

    def __init__(
        self,
        repository: DatasetRepository,
        path: Path,
        connection: sqlite3.Connection,
        metadata: IndexMetadata,
    ):
        self.repository = repository
        self.path = path
        self._connection = connection
        self._connection.create_function(
            "CASEFOLD",
            1,
            lambda value: str(value).casefold(),
            deterministic=True,
        )
        self._connection.create_function(
            "ISO_TIMESTAMP",
            1,
            lambda value: datetime.fromisoformat(str(value)).timestamp(),
            deterministic=True,
        )
        self.metadata = metadata

    @classmethod
    def open(
        cls, repository: DatasetRepository, path: Path | None = None, *, require_valid: bool = True
    ) -> "RepositoryIndex | None":
        resolved = path or index_path(repository.root)
        if not resolved.is_file():
            if require_valid:
                raise IndexNotFoundError(f"index does not exist: {resolved}")
            return None
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(resolved)
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT value FROM metadata WHERE key='metadata'").fetchone()
            complete = connection.execute(
                "SELECT value FROM metadata WHERE key='complete'"
            ).fetchone()
            if row is None or complete is None or complete[0] != "1":
                raise IndexCorruptionError("index is incomplete")
            payload = json.loads(row[0])
            metadata = IndexMetadata(
                format_version=int(payload["format_version"]),
                compatibility_version=str(payload["compatibility_version"]),
                schema_version=int(payload["schema_version"]),
                repository_identity=str(payload["repository_identity"]),
                files=dict(payload["files"]),
                profile_fingerprints=dict(payload["profile_fingerprints"]),
                blocklist_fingerprints=dict(payload["blocklist_fingerprints"]),
                record_counts=dict(payload["record_counts"]),
                capabilities=tuple(payload["capabilities"]),
                builder_version=str(payload["builder_version"]),
                completed=bool(payload["completed"]),
            )
            cls._validate_metadata(repository, metadata)
            errors = sqlite_integrity_errors(connection)
            if errors:
                raise IndexCorruptionError(f"SQLite integrity check failed: {'; '.join(errors)}")
            return cls(repository, resolved, connection, metadata)
        except RepositoryIndexError:
            if connection is not None:
                connection.close()
            if require_valid:
                raise
            return None
        except (OSError, sqlite3.Error, KeyError, TypeError, ValueError) as error:
            if connection is not None:
                connection.close()
            if require_valid:
                raise IndexCorruptionError(f"invalid index {resolved}: {error}") from error
            return None

    @classmethod
    def status(cls, repository: DatasetRepository, path: Path | None = None) -> IndexStatus:
        resolved = path or index_path(repository.root)
        if not resolved.is_file():
            return IndexStatus(str(resolved), False, False, "missing", None, "index not found")
        try:
            opened = cls.open(repository, resolved)
            assert opened is not None
            try:
                return IndexStatus(str(resolved), True, True, "valid", opened.metadata)
            finally:
                opened.close()
        except IndexStaleError as error:
            return IndexStatus(str(resolved), True, False, "stale", None, str(error))
        except RepositoryIndexError as error:
            return IndexStatus(str(resolved), True, False, "invalid", None, str(error))

    @staticmethod
    def _validate_metadata(repository: DatasetRepository, metadata: IndexMetadata) -> None:
        if metadata.format_version != FORMAT_VERSION:
            raise IndexCompatibilityError("unsupported index format version")
        if metadata.schema_version != DATASET_SCHEMA_VERSION:
            raise IndexCompatibilityError("index dataset schema is incompatible")
        if metadata.compatibility_version != compatibility_fingerprint(repository):
            raise IndexCompatibilityError("index compatibility fingerprint differs")
        current = file_fingerprints(repository)
        if current != metadata.files:
            changed = sorted(
                set(current) ^ set(metadata.files)
                | {key for key in current if current.get(key) != metadata.files.get(key)}
            )
            raise IndexStaleError("canonical files changed: " + ", ".join(changed))
        if repository_identity(current) != metadata.repository_identity:
            raise IndexStaleError("repository identity differs")

    def close(self) -> None:
        self._connection.close()

    @property
    def is_valid(self) -> bool:
        return True

    def __enter__(self) -> "RepositoryIndex":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _row(self, row: sqlite3.Row | tuple[Any, ...]) -> IndexedCandidate:
        values = dict(row) if isinstance(row, sqlite3.Row) else {}
        if not values:
            names = [item[1] for item in self._connection.execute("PRAGMA table_info(candidates)")]
            values = dict(zip(names, row, strict=True))
        latest_review = (
            ReviewRecord.model_validate_json(values["latest_review_json"])
            if values.get("latest_review_json")
            else None
        )
        return IndexedCandidate(
            candidate=WordCandidate.model_validate_json(values["candidate_json"]),
            normalized_word=values["normalized_word"],
            release_eligible=bool(values["release_eligible"]),
            eligibility_reasons=tuple(json.loads(values["eligibility_reasons"])),
            blocklist_match=bool(values["blocklist_match"]),
            review_state=(
                "pending"
                if latest_review is None
                else "flagged"
                if latest_review.flags
                else "complete"
            ),
            reviewer=latest_review.reviewer_id if latest_review else None,
        )

    @staticmethod
    def _candidate_projection() -> str:
        return (
            "c.*, (SELECT r.record_json FROM reviews r WHERE r.candidate_id=c.id "
            "ORDER BY ISO_TIMESTAMP(r.reviewed_at) DESC, r.id DESC LIMIT 1) AS latest_review_json"
        )

    def get_candidate(self, candidate_id: str) -> IndexedCandidate | None:
        row = self._connection.execute(
            f"SELECT {self._candidate_projection()} FROM candidates c WHERE c.id=?",
            (candidate_id,),
        ).fetchone()
        return self._row(row) if row else None

    def find_by_normalized_word(
        self, language: str, normalized_word: str
    ) -> tuple[IndexedCandidate, ...]:
        rows = self._connection.execute(
            f"SELECT {self._candidate_projection()} FROM candidates c "
            "WHERE c.language=? AND c.normalized_word=? ORDER BY c.id",
            (language, normalized_word),
        ).fetchall()
        return tuple(self._row(row) for row in rows)

    def search_candidates(
        self,
        query: str = "",
        *,
        language: str | None = None,
        category: str | None = None,
        status: CandidateStatus | str | None = None,
        release_eligible: bool | None = None,
        review_state: str | None = None,
        contributor: str | None = None,
        reviewer: str | None = None,
        source_type: str | None = None,
        license_eligible: bool | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        modified_after: datetime | None = None,
        modified_before: datetime | None = None,
        similarity_warning: bool | None = None,
        blocklist_state: str | None = None,
        include_normalized_search: bool = False,
        sort_field: str = "id",
        reverse: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> IndexQueryPage:
        clauses: list[str] = []
        values: list[Any] = []
        if query:
            fields = "c.word || ' ' || c.id"
            if include_normalized_search:
                fields = "c.word || ' ' || c.normalized_word || ' ' || c.id"
            clauses.append(f"INSTR(CASEFOLD({fields}), CASEFOLD(?)) > 0")
            values.append(query)
        if language:
            clauses.append("c.language=?")
            values.append(language)
        if category:
            clauses.append("c.category=?")
            values.append(category)
        if status:
            clauses.append("c.status=?")
            values.append(status.value if isinstance(status, CandidateStatus) else status)
        if release_eligible is not None:
            clauses.append("c.release_eligible=?")
            values.append(int(release_eligible))
        latest_review = (
            "(SELECT r.record_json FROM reviews r WHERE r.candidate_id=c.id "
            "ORDER BY ISO_TIMESTAMP(r.reviewed_at) DESC, r.id DESC LIMIT 1)"
        )
        if review_state == "pending":
            clauses.append(f"{latest_review} IS NULL")
        elif review_state == "flagged":
            clauses.append(f"JSON_ARRAY_LENGTH({latest_review}, '$.flags') > 0")
        elif review_state == "complete":
            clauses.append(
                f"{latest_review} IS NOT NULL AND JSON_ARRAY_LENGTH({latest_review}, '$.flags') = 0"
            )
        if contributor is not None:
            clauses.append("c.submitted_by=?")
            values.append(contributor)
        if reviewer is not None:
            clauses.append(f"JSON_EXTRACT({latest_review}, '$.reviewer_id')=?")
            values.append(reviewer)
        if source_type is not None:
            clauses.append("c.source_type=?")
            values.append(source_type)
        if license_eligible is not None:
            clauses.append("c.license_eligible=?")
            values.append(int(license_eligible))
        for field, lower, upper in (
            ("submitted_at", created_after, created_before),
            ("reviewed_at", modified_after, modified_before),
        ):
            if lower is not None:
                clauses.append(f"c.{field} IS NOT NULL AND ISO_TIMESTAMP(c.{field})>=?")
                values.append(lower.timestamp())
            if upper is not None:
                clauses.append(f"c.{field} IS NOT NULL AND ISO_TIMESTAMP(c.{field})<=?")
                values.append(upper.timestamp())
        if similarity_warning is not None:
            clauses.append("0=?")
            values.append(int(similarity_warning))
        if blocklist_state is not None:
            clauses.append("c.blocklist_match=?")
            values.append(int(blocklist_state == "match"))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        total = int(
            self._connection.execute(
                f"SELECT COUNT(*) FROM candidates c{where}", values
            ).fetchone()[0]
        )
        sort_columns = {
            "id": ("c.id",),
            "word": ("c.normalized_word", "c.id"),
            "language": ("c.language", "c.normalized_word", "c.id"),
            "category": ("COALESCE(c.category, '')", "c.normalized_word", "c.id"),
            "status": ("c.status", "c.normalized_word", "c.id"),
            "eligible": ("c.release_eligible", "c.normalized_word", "c.id"),
        }
        try:
            columns = sort_columns[sort_field]
        except KeyError as error:
            raise ValueError(f"unsupported candidate sort: {sort_field}") from error
        direction = "DESC" if reverse else "ASC"
        order = ", ".join(f"{column} {direction}" for column in columns)
        rows = self._connection.execute(
            f"SELECT {self._candidate_projection()} FROM candidates c{where} "
            f"ORDER BY {order} LIMIT ? OFFSET ?",
            (*values, limit, offset),
        ).fetchall()
        return IndexQueryPage(tuple(self._row(row) for row in rows), total, offset, limit)

    def list_languages(self) -> tuple[str, ...]:
        rows = self._connection.execute(
            "SELECT DISTINCT language FROM candidates ORDER BY language"
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def list_categories(self) -> tuple[str, ...]:
        rows = self._connection.execute(
            "SELECT DISTINCT category FROM candidates WHERE category IS NOT NULL ORDER BY category"
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def count_candidates(self, **filters: Any) -> int:
        return self.search_candidates(limit=1, **filters).total

    def get_provenance(self, candidate_id: str) -> tuple[ProvenanceRecord, ...]:
        rows = self._connection.execute(
            "SELECT record_json FROM provenance WHERE candidate_id=? ORDER BY id", (candidate_id,)
        ).fetchall()
        return tuple(ProvenanceRecord.model_validate_json(row[0]) for row in rows)

    def get_reviews(self, candidate_id: str) -> tuple[ReviewRecord, ...]:
        rows = self._connection.execute(
            "SELECT record_json FROM reviews WHERE candidate_id=? "
            "ORDER BY ISO_TIMESTAMP(reviewed_at), id",
            (candidate_id,),
        ).fetchall()
        return tuple(ReviewRecord.model_validate_json(row[0]) for row in rows)

    def get_dashboard_statistics(self) -> dict[str, Any]:
        def grouped(expression: str, *, table: str = "candidates") -> dict[str, int]:
            rows = self._connection.execute(
                f"SELECT {expression}, COUNT(*) FROM {table} "
                f"GROUP BY {expression} ORDER BY {expression}"
            ).fetchall()
            return {str(row[0]): int(row[1]) for row in rows}

        statuses = grouped("status")
        total = int(self._connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0])
        eligible = int(
            self._connection.execute(
                "SELECT COUNT(*) FROM candidates WHERE release_eligible=1"
            ).fetchone()[0]
        )
        latest_review = (
            "(SELECT r.record_json FROM reviews r WHERE r.candidate_id=c.id "
            "ORDER BY ISO_TIMESTAMP(r.reviewed_at) DESC, r.id DESC LIMIT 1)"
        )
        review_time_rows = self._connection.execute(
            "SELECT c.submitted_at, r.reviewed_at FROM reviews r "
            "JOIN candidates c ON c.id=r.candidate_id "
            "WHERE c.submitted_at IS NOT NULL "
            "ORDER BY c.language, c.normalized_word, c.id, ISO_TIMESTAMP(r.reviewed_at), r.id"
        ).fetchall()
        review_times = [
            (
                datetime.fromisoformat(str(reviewed_at)) - datetime.fromisoformat(str(submitted_at))
            ).total_seconds()
            for submitted_at, reviewed_at in review_time_rows
        ]
        return {
            "total_candidates": total,
            "languages": grouped("language"),
            "categories": grouped("COALESCE(category, 'uncategorized')"),
            "statuses": statuses,
            "approved": statuses.get("approved", 0),
            "pending_reviews": statuses.get("submitted", 0) + statuses.get("needs_review", 0),
            "flagged": int(
                self._connection.execute(
                    f"SELECT COUNT(*) FROM candidates c WHERE "
                    f"JSON_ARRAY_LENGTH({latest_review}, '$.flags') > 0"
                ).fetchone()[0]
            ),
            "release_eligible": eligible,
            "release_blocked": total - eligible,
            "provenance_missing": int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM candidates c WHERE NOT EXISTS "
                    "(SELECT 1 FROM provenance p WHERE p.candidate_id=c.id)"
                ).fetchone()[0]
            ),
            "duplicate_warnings": int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM candidates WHERE eligibility_reasons LIKE '%duplicate%'"
                ).fetchone()[0]
            ),
            "blocklist_matches": int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM candidates WHERE blocklist_match=1"
                ).fetchone()[0]
            ),
            "license_distribution": dict(
                sorted(
                    {
                        ("eligible" if key == "1" else "ineligible"): value
                        for key, value in grouped("license_eligible").items()
                    }.items()
                )
            ),
            "contributors": grouped("COALESCE(submitted_by, 'unknown')"),
            "reviewers": grouped("JSON_EXTRACT(record_json, '$.reviewer_id')", table="reviews"),
            "average_review_time_seconds": (
                sum(review_times) / len(review_times) if review_times else None
            ),
        }

    def find_similarity_candidates(
        self, candidate_id: str, limit: int = 100
    ) -> tuple[IndexedCandidate, ...]:
        candidate = self.get_candidate(candidate_id)
        if candidate is None:
            return ()
        prefix = candidate.normalized_word[:2]
        rows = self._connection.execute(
            f"SELECT {self._candidate_projection()} FROM candidates c "
            "WHERE c.language=? AND c.id<>? "
            "AND c.normalized_word LIKE ? ORDER BY c.normalized_word, c.id LIMIT ?",
            (candidate.candidate.language, candidate_id, prefix + "%", limit),
        ).fetchall()
        return tuple(self._row(row) for row in rows)


__all__ = ["RepositoryIndex"]
