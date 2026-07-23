"""Typed, backend-neutral read API over the disposable SQLite index."""

import json
import sqlite3
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
from .storage import index_path


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
                created_at=payload.get("created_at"),
            )
            cls._validate_metadata(repository, metadata)
            connection.execute("PRAGMA integrity_check").fetchone()
            return cls(repository, resolved, connection, metadata)
        except RepositoryIndexError:
            connection.close()
            if require_valid:
                raise
            return None
        except (OSError, sqlite3.Error, KeyError, TypeError, ValueError) as error:
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
            return IndexStatus(str(resolved), True, True, "valid", opened.metadata)
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
        if query:
            clauses.append("(word LIKE ? OR normalized_word LIKE ? OR id LIKE ?)")
            needle = f"%{query}%"
            values.extend((needle, needle, needle))
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
        total = int(
            self._connection.execute(f"SELECT COUNT(*) FROM candidates{where}", values).fetchone()[
                0
            ]
        )
        rows = self._connection.execute(
            f"SELECT * FROM candidates{where} ORDER BY normalized_word, id LIMIT ? OFFSET ?",
            (*values, limit, offset),
        ).fetchall()
        return IndexQueryPage(tuple(self._row(row) for row in rows), total, offset, limit)

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

    def get_dashboard_statistics(self, **_: Any) -> dict[str, Any]:
        rows = self._connection.execute(
            "SELECT status, COUNT(*) FROM candidates GROUP BY status ORDER BY status"
        ).fetchall()
        status_counts = {row[0]: row[1] for row in rows}
        return {
            "total_candidates": int(
                self._connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
            ),
            "statuses": status_counts,
            "release_eligible": int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM candidates WHERE release_eligible=1"
                ).fetchone()[0]
            ),
            "release_blocked": int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM candidates WHERE release_eligible=0"
                ).fetchone()[0]
            ),
            "blocklist_matches": int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM candidates WHERE blocklist_match=1"
                ).fetchone()[0]
            ),
            "provenance_missing": int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM candidates c "
                    "WHERE NOT EXISTS (SELECT 1 FROM provenance p "
                    "WHERE p.candidate_id=c.id)"
                ).fetchone()[0]
            ),
        }

    def find_similarity_candidates(
        self, candidate_id: str, threshold: int = 1, limit: int = 100
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
