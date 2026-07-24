"""Full builders for the disposable SQLite index."""

import json
import os
import sqlite3
import tempfile
from collections.abc import Callable
from pathlib import Path

from ..blocklists import load_blocklists_with_metadata
from ..curation import evaluate_release_eligibility, load_curation_data
from ..models import ProvenanceRecord
from ..moderation import latest_reviews
from ..normalize import normalize_word
from ..profiles import load_policy, load_profiles
from ..repository import DATASET_SCHEMA_VERSION, TOOL_VERSION, DatasetRepository
from .errors import IndexBuildError
from .metadata import (
    FORMAT_VERSION,
    compatibility_fingerprint,
    file_fingerprints,
    profile_fingerprints,
    repository_identity,
)
from .model import IndexMetadata
from .storage import build_lock, index_path, sqlite_integrity_errors

Progress = Callable[[str, int, int], None]


SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE candidates (
 id TEXT PRIMARY KEY, language TEXT NOT NULL, word TEXT NOT NULL,
 normalized_word TEXT NOT NULL, category TEXT, status TEXT NOT NULL,
 submitted_at TEXT, reviewed_at TEXT, submitted_by TEXT, reviewed_by TEXT,
 source_type TEXT NOT NULL, license_eligible INTEGER NOT NULL,
 release_eligible INTEGER NOT NULL, eligibility_reasons TEXT NOT NULL,
 blocklist_match INTEGER NOT NULL, score INTEGER, candidate_json TEXT NOT NULL
);
CREATE TABLE provenance (
 id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, record_json TEXT NOT NULL
);
CREATE TABLE reviews (
 id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, reviewed_at TEXT NOT NULL,
 record_json TEXT NOT NULL
);
CREATE INDEX candidates_normalized ON candidates(language, normalized_word);
CREATE INDEX candidates_search ON candidates(language, normalized_word, word);
CREATE INDEX candidates_filters ON candidates(status, category, release_eligible);
CREATE INDEX provenance_candidate ON provenance(candidate_id);
CREATE INDEX reviews_candidate ON reviews(candidate_id, reviewed_at, id);
CREATE TABLE similarity_cache (
 cache_key TEXT PRIMARY KEY, candidate_a TEXT NOT NULL, candidate_b TEXT NOT NULL,
 algorithm TEXT NOT NULL, result_json TEXT NOT NULL
);
"""


class RepositoryIndexBuilder:
    """Build a verified index from canonical repository files."""

    def __init__(self, repository: DatasetRepository, index_root: Path | None = None):
        self.repository = repository
        self.path = index_path(repository.root, index_root)

    def build(self, progress: Progress | None = None) -> IndexMetadata:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with build_lock(self.path):
            files = file_fingerprints(self.repository)
            errors = self.repository.validate_layout()
            if errors:
                raise IndexBuildError("cannot index invalid repository: " + "; ".join(errors))
            metadata = self._metadata(files)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix="index-", suffix=".sqlite3", dir=self.path.parent
            )
            os.close(descriptor)
            temporary = Path(temporary_name)
            try:
                self._build_database(temporary, metadata, progress)
                final_files = file_fingerprints(self.repository)
                if final_files != files:
                    changed = sorted(
                        set(final_files) ^ set(files)
                        | {key for key in final_files if final_files.get(key) != files.get(key)}
                    )
                    raise IndexBuildError(
                        "canonical repository changed during index build: " + ", ".join(changed)
                    )
                self._verify_database(temporary)
                os.replace(temporary, self.path)
            except Exception as error:
                temporary.unlink(missing_ok=True)
                if isinstance(error, IndexBuildError):
                    raise
                raise IndexBuildError(f"index build failed: {error}") from error
        return metadata

    def refresh(self, progress: Progress | None = None) -> tuple[IndexMetadata, str]:
        """Refresh safely; full rebuild is used when any canonical file changed."""
        from .repository_index import RepositoryIndex

        current = RepositoryIndex.open(self.repository, self.path, require_valid=False)
        if current is not None and current.is_valid:
            files = file_fingerprints(self.repository)
            if files == current.metadata.files:
                return current.metadata, "unchanged"
        return self.build(progress), "full_rebuild"

    def _metadata(self, files: dict[str, str]) -> IndexMetadata:
        counts = {"candidates": 0, "provenance": 0, "reviews": 0}
        for language in self.repository.load_manifest().supported_languages:
            _, candidates, provenance, reviews = load_curation_data(language, self.repository.root)
            counts["candidates"] += len(candidates)
            counts["provenance"] += len(provenance)
            counts["reviews"] += len(reviews)
        return IndexMetadata(
            format_version=FORMAT_VERSION,
            compatibility_version=compatibility_fingerprint(self.repository),
            schema_version=DATASET_SCHEMA_VERSION,
            repository_identity=repository_identity(files),
            files=files,
            profile_fingerprints=profile_fingerprints(self.repository),
            blocklist_fingerprints={
                key: value for key, value in files.items() if "blocklists/" in key
            },
            record_counts=counts,
            capabilities=(
                "candidate_lookup",
                "search",
                "filters",
                "statistics",
                "similarity_candidates",
            ),
            builder_version=TOOL_VERSION,
            completed=True,
        )

    def _build_database(
        self, path: Path, metadata: IndexMetadata, progress: Progress | None
    ) -> None:
        connection = sqlite3.connect(path)
        try:
            connection.executescript(SCHEMA)
            connection.execute("BEGIN")
            connection.executemany(
                "INSERT INTO metadata(key,value) VALUES (?,?)",
                (("metadata", metadata.to_json()), ("complete", "1")),
            )
            profiles = load_profiles(self.repository.root)
            policy = load_policy(self.repository.root)
            total = metadata.record_counts["candidates"]
            done = 0
            for language in sorted(profiles):
                profile, records, provenance, reviews = load_curation_data(
                    language, self.repository.root
                )
                _, matches, all_words = load_blocklists_with_metadata(
                    self.repository.root / "languages" / language / "blocklists", profile
                )
                error_words = {item.word for item in matches if item.severity == "error"}
                latest = latest_reviews(reviews)
                provenance_by_candidate: dict[str, list[ProvenanceRecord]] = {}
                for item in provenance:
                    provenance_by_candidate.setdefault(item.candidate_id, []).append(item)
                for record in records:
                    candidate = record.candidate
                    candidate_provenance = sorted(
                        provenance_by_candidate.get(candidate.id, []), key=lambda item: item.id
                    )
                    review = latest.get(candidate.id)
                    reasons = evaluate_release_eligibility(
                        record,
                        candidate_provenance[-1] if candidate_provenance else None,
                        review,
                        policy.required_review_criteria,
                        error_words,
                    )
                    normalized = normalize_word(candidate.word, profile)
                    connection.execute(
                        "INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            candidate.id,
                            candidate.language,
                            candidate.word,
                            normalized,
                            candidate.category,
                            candidate.status.value,
                            candidate.submitted_at.isoformat() if candidate.submitted_at else None,
                            candidate.reviewed_at.isoformat() if candidate.reviewed_at else None,
                            candidate.submitted_by,
                            candidate.reviewed_by,
                            candidate.source_type.value,
                            int(candidate.is_license_eligible),
                            int(not reasons),
                            json.dumps(reasons, ensure_ascii=False),
                            int(candidate.word in all_words),
                            candidate.score,
                            candidate.model_dump_json(),
                        ),
                    )
                    for provenance_item in candidate_provenance:
                        connection.execute(
                            "INSERT INTO provenance VALUES (?,?,?)",
                            (
                                provenance_item.id,
                                provenance_item.candidate_id,
                                provenance_item.model_dump_json(),
                            ),
                        )
                    for review_item in reviews:
                        if review_item.candidate_id == candidate.id:
                            connection.execute(
                                "INSERT INTO reviews VALUES (?,?,?,?)",
                                (
                                    review_item.id,
                                    review_item.candidate_id,
                                    review_item.reviewed_at.isoformat(),
                                    review_item.model_dump_json(),
                                ),
                            )
                    done += 1
                    if progress:
                        progress(language, done, total)
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _verify_database(path: Path) -> None:
        connection = sqlite3.connect(path)
        try:
            complete = connection.execute(
                "SELECT value FROM metadata WHERE key='complete'"
            ).fetchone()
            if complete != ("1",):
                raise IndexBuildError("index completion marker is missing")
            errors = sqlite_integrity_errors(connection)
            if errors:
                raise IndexBuildError(f"SQLite integrity check failed: {'; '.join(errors)}")
        finally:
            connection.close()
