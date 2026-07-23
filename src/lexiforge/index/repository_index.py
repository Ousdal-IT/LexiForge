"""Typed, backend-neutral read API over the disposable SQLite index."""

import json
import sqlite3
from collections import Counter
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
        return IndexedCandidate(
            candidate=WordCandidate.model_validate_json(values["candidate_json"]),
            normalized_word=values["normalized_word"],
            release_eligible=bool(values["release_eligible"]),
            eligibility_reasons=tuple(json.loads(values["eligibility_reasons"])),
            blocklist_match=bool(values["blocklist_match"]),
        )

    def get_candidate(self, candidate_id: str) -> IndexedCandidate | None:
        row = self._connection.execute(
            "SELECT * FROM candidates WHERE id=?", (candidate_id,)
        ).fetchone()
        return self._row(row) if row else None

    def find_by_normalized_word(
        self, language: str, normalized_word: str
    ) -> tuple[IndexedCandidate, ...]:
        rows = self._connection.execute(
            "SELECT * FROM candidates WHERE language=? AND normalized_word=? ORDER BY id",
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
        limit: int = 50,
        offset: int = 0,
    ) -> IndexQueryPage:
        clauses: list[str] = []
        values: list[Any] = []
        if language:
            clauses.append("language=?")
            values.append(language)
        if category:
            clauses.append("category=?")
            values.append(category)
        if status:
            clauses.append("status=?")
            values.append(status.value if isinstance(status, CandidateStatus) else status)
        if release_eligible is not None:
            clauses.append("release_eligible=?")
            values.append(int(release_eligible))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self._connection.execute(
            f"SELECT * FROM candidates{where} ORDER BY id", values
        ).fetchall()
        if query:
            folded = query.casefold()
            rows = [row for row in rows if folded in f"{row['word']} {row['id']}".casefold()]
        total = len(rows)
        selected = rows[offset : offset + limit]
        return IndexQueryPage(tuple(self._row(row) for row in selected), total, offset, limit)

    def count_candidates(self, **filters: Any) -> int:
        return self.search_candidates(limit=1, **filters).total

    def get_provenance(self, candidate_id: str) -> tuple[ProvenanceRecord, ...]:
        rows = self._connection.execute(
            "SELECT record_json FROM provenance WHERE candidate_id=? ORDER BY id", (candidate_id,)
        ).fetchall()
        return tuple(ProvenanceRecord.model_validate_json(row[0]) for row in rows)

    def get_reviews(self, candidate_id: str) -> tuple[ReviewRecord, ...]:
        rows = self._connection.execute(
            "SELECT record_json FROM reviews WHERE candidate_id=? ORDER BY reviewed_at, id",
            (candidate_id,),
        ).fetchall()
        return tuple(ReviewRecord.model_validate_json(row[0]) for row in rows)

    def get_dashboard_statistics(self) -> dict[str, Any]:
        candidate_rows = self._connection.execute(
            "SELECT * FROM candidates ORDER BY language, normalized_word, id"
        ).fetchall()
        candidates = [self._row(row) for row in candidate_rows]
        provenance_counts = Counter(
            row[0]
            for row in self._connection.execute(
                "SELECT candidate_id FROM provenance ORDER BY candidate_id, id"
            ).fetchall()
        )
        review_rows = self._connection.execute(
            "SELECT candidate_id, record_json FROM reviews ORDER BY candidate_id, reviewed_at, id"
        ).fetchall()
        reviews_by_candidate: dict[str, list[ReviewRecord]] = {}
        for row in review_rows:
            reviews_by_candidate.setdefault(row[0], []).append(
                ReviewRecord.model_validate_json(row[1])
            )
        statuses = Counter(item.candidate.status.value for item in candidates)
        review_times: list[float] = []
        for item in candidates:
            submitted = item.candidate.submitted_at
            if submitted is None:
                continue
            for review in reviews_by_candidate.get(item.candidate.id, ()):
                review_times.append((review.reviewed_at - submitted).total_seconds())
        return {
            "total_candidates": len(candidates),
            "languages": dict(
                sorted(Counter(item.candidate.language for item in candidates).items())
            ),
            "categories": dict(
                sorted(
                    Counter(
                        item.candidate.category or "uncategorized" for item in candidates
                    ).items()
                )
            ),
            "statuses": dict(sorted(statuses.items())),
            "approved": statuses["approved"],
            "pending_reviews": sum(
                item.candidate.status.value in {"submitted", "needs_review"} for item in candidates
            ),
            "flagged": sum(
                bool(reviews_by_candidate.get(item.candidate.id))
                and bool(reviews_by_candidate[item.candidate.id][-1].flags)
                for item in candidates
            ),
            "release_eligible": sum(item.release_eligible for item in candidates),
            "release_blocked": sum(not item.release_eligible for item in candidates),
            "provenance_missing": sum(
                not provenance_counts[item.candidate.id] for item in candidates
            ),
            "duplicate_warnings": sum(
                "duplicate" in reason for item in candidates for reason in item.eligibility_reasons
            ),
            "blocklist_matches": sum(item.blocklist_match for item in candidates),
            "license_distribution": dict(
                sorted(
                    Counter(
                        "eligible" if item.candidate.is_license_eligible else "ineligible"
                        for item in candidates
                    ).items()
                )
            ),
            "contributors": dict(
                sorted(
                    Counter(item.candidate.submitted_by or "unknown" for item in candidates).items()
                )
            ),
            "reviewers": dict(
                sorted(
                    Counter(
                        review.reviewer_id
                        for reviews in reviews_by_candidate.values()
                        for review in reviews
                    ).items()
                )
            ),
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
            "SELECT * FROM candidates WHERE language=? AND id<>? "
            "AND normalized_word LIKE ? ORDER BY normalized_word, id LIMIT ?",
            (candidate.candidate.language, candidate_id, prefix + "%", limit),
        ).fetchall()
        return tuple(self._row(row) for row in rows)


__all__ = ["RepositoryIndex"]
