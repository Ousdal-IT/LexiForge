import csv
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from lexiforge.cli import app
from lexiforge.constants import DEFAULT_DATA_ROOT
from lexiforge.curation import load_curation_data
from lexiforge.index import (
    IndexBuildError,
    IndexCorruptionError,
    IndexLockError,
    IndexStaleError,
    RepositoryIndex,
    RepositoryIndexBuilder,
    SimilarityCache,
    cache_key,
)
from lexiforge.index.storage import build_lock, index_path
from lexiforge.normalize import normalize_word
from lexiforge.repository import DatasetRepository
from lexiforge.workbench.model import RepositorySnapshot
from lexiforge.workbench.tools import repository_statistics

runner = CliRunner()


def repository_copy(tmp_path: Path) -> DatasetRepository:
    root = tmp_path / "data"
    shutil.copytree(DEFAULT_DATA_ROOT, root)
    return DatasetRepository(root)


def _candidate_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


def _write_candidate_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _append_candidates(repository: DatasetRepository, words: list[str]) -> list[str]:
    path = repository.root / "languages/nb/candidates.csv"
    fieldnames, rows = _candidate_rows(path)
    template = dict(rows[0])
    identifiers: list[str] = []
    for number, word in enumerate(words, 1):
        identifier = f"90000000-0000-4000-8000-{number:012d}"
        row = dict(template)
        row.update(
            {
                "id": identifier,
                "word": word,
                "status": "submitted",
                "reviewed_at": "",
                "score": "",
                "notes": "M4 parity fixture",
            }
        )
        rows.append(row)
        identifiers.append(identifier)
    _write_candidate_rows(path, fieldnames, rows)
    return identifiers


def _canonical_candidate_ids(
    repository: DatasetRepository,
    language: str,
    *,
    search: str = "",
    status: str | None = None,
    category: str | None = None,
) -> list[str]:
    _, records, _, _ = load_curation_data(language, repository.root)
    folded = search.casefold()
    return [
        item.candidate.id
        for item in sorted(records, key=lambda item: item.candidate.id)
        if (not search or folded in f"{item.candidate.word} {item.candidate.id}".casefold())
        and (status is None or item.candidate.status.value == status)
        and (category is None or item.candidate.category == category)
    ]


def _indexed_candidate_ids(
    repository: DatasetRepository,
    index_root: Path,
    *,
    search: str = "",
    status: str | None = None,
    category: str | None = None,
) -> list[str]:
    with RepositoryIndex.open(repository, index_path(repository.root, index_root)) as index:
        page = index.search_candidates(
            search,
            language="nb",
            status=status,
            category=category,
            limit=100_000,
        )
        return [item.candidate.id for item in page.items]


def test_full_index_build_and_query_parity(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    metadata = RepositoryIndexBuilder(repository, index_root).build()
    assert metadata.record_counts == {"candidates": 72, "provenance": 72, "reviews": 48}
    snapshot = RepositorySnapshot.load(repository)
    with RepositoryIndex.open(repository, index_path(repository.root, index_root)) as index:
        assert index.count_candidates() == 72
        assert index.get_candidate("10000000-0000-4000-8000-000000000001") is not None
        assert index.find_by_normalized_word("nb", "bjørn")[0].candidate.word == "bjørn"
        assert index.get_provenance("10000000-0000-4000-8000-000000000001")
        assert index.get_reviews("10000000-0000-4000-8000-000000000001")
        assert index.get_dashboard_statistics() == repository_statistics(snapshot).as_dict()
        for canonical in snapshot.candidates:
            indexed = index.get_candidate(canonical.candidate.id)
            assert indexed is not None
            assert indexed.candidate == canonical.candidate
            assert indexed.normalized_word == canonical.normalized_word
            assert indexed.release_eligible == canonical.release_eligible
            assert indexed.eligibility_reasons == canonical.eligibility_reasons
            assert indexed.blocklist_match == canonical.blocklist_match
            assert index.get_provenance(canonical.candidate.id) == canonical.provenance
            assert index.get_reviews(canonical.candidate.id) == canonical.reviews


@pytest.mark.parametrize(
    ("search", "status", "category"),
    [
        ("", None, None),
        ("B", None, None),
        ("bjØRN", "approved", "animals"),
        ("missing", None, None),
        ("", "submitted", None),
    ],
)
def test_search_filter_and_ordering_match_canonical_fallback(
    tmp_path: Path, search: str, status: str | None, category: str | None
) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    RepositoryIndexBuilder(repository, index_root).build()
    assert _indexed_candidate_ids(
        repository, index_root, search=search, status=status, category=category
    ) == _canonical_candidate_ids(repository, "nb", search=search, status=status, category=category)


def test_unicode_normalization_casefold_and_duplicate_parity(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    composed = "BLÅ"
    decomposed = "BLA\u030a"
    identifiers = _append_candidates(repository, [composed, decomposed, "Straße"])
    index_root = tmp_path / "index"
    RepositoryIndexBuilder(repository, index_root).build()

    for query in ("blå", "bla\u030a", "STRASSE", "straße"):
        assert _indexed_candidate_ids(repository, index_root, search=query) == (
            _canonical_candidate_ids(repository, "nb", search=query)
        )

    profile, records, _, _ = load_curation_data("nb", repository.root)
    canonical_duplicates = sorted(
        item.candidate.id
        for item in records
        if normalize_word(item.candidate.word, profile) == "blå"
    )
    with RepositoryIndex.open(repository, index_path(repository.root, index_root)) as index:
        indexed_duplicates = [
            item.candidate.id for item in index.find_by_normalized_word("nb", "blå")
        ]
    assert identifiers[:2] == canonical_duplicates[-2:]
    assert indexed_duplicates == canonical_duplicates


def test_metadata_is_deterministic(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    first = RepositoryIndexBuilder(repository, tmp_path / "one").build()
    second = RepositoryIndexBuilder(repository, tmp_path / "two").build()
    assert first.to_json() == second.to_json()
    assert "created_at" not in first.as_dict()


def test_stale_index_is_rejected_and_refresh_rebuilds(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    RepositoryIndexBuilder(repository, index_root).build()
    candidate_path = repository.root / "languages/nb/candidates.csv"
    candidate_path.write_bytes(candidate_path.read_bytes() + b"\n")
    with pytest.raises(IndexStaleError):
        RepositoryIndex.open(repository, index_path(repository.root, index_root))
    metadata, strategy = RepositoryIndexBuilder(repository, index_root).refresh()
    assert strategy == "full_rebuild"
    assert metadata.completed


def test_repository_change_during_build_preserves_previous_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    builder = RepositoryIndexBuilder(repository, index_root)
    builder.build()
    location = index_path(repository.root, index_root)
    previous = location.read_bytes()
    original = builder._build_database

    def change_repository(*args: Any, **kwargs: Any) -> None:
        original(*args, **kwargs)
        path = repository.root / "languages/nb/candidates.csv"
        path.write_bytes(path.read_bytes() + b"\n")

    monkeypatch.setattr(builder, "_build_database", change_repository)
    with pytest.raises(IndexBuildError, match="changed during index build"):
        builder.build()
    assert location.read_bytes() == previous
    assert not tuple(location.parent.glob("index-*.sqlite3"))


def test_interrupted_build_preserves_previous_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    builder = RepositoryIndexBuilder(repository, index_root)
    builder.build()
    location = index_path(repository.root, index_root)
    previous = location.read_bytes()

    def interrupt(*_: Any, **__: Any) -> None:
        raise RuntimeError("interrupted")

    monkeypatch.setattr(builder, "_build_database", interrupt)
    with pytest.raises(IndexBuildError, match="interrupted"):
        builder.build()
    assert location.read_bytes() == previous
    assert not tuple(location.parent.glob("index-*.sqlite3"))


def test_corrupt_sqlite_and_incomplete_metadata_are_rejected(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    builder = RepositoryIndexBuilder(repository, index_root)
    builder.build()
    location = index_path(repository.root, index_root)

    connection = sqlite3.connect(location)
    connection.execute("DELETE FROM metadata WHERE key='complete'")
    connection.commit()
    connection.close()
    with pytest.raises(IndexCorruptionError, match="incomplete"):
        RepositoryIndex.open(repository, location)

    location.write_bytes(b"not a SQLite database")
    with pytest.raises(IndexCorruptionError, match="invalid index"):
        RepositoryIndex.open(repository, location)


def test_failed_integrity_check_rejects_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    monkeypatch.setattr(
        "lexiforge.index.builder.sqlite_integrity_errors", lambda _: ("page 2 is corrupt",)
    )
    with pytest.raises(IndexBuildError, match="page 2 is corrupt"):
        RepositoryIndexBuilder(repository, index_root).build()
    location = index_path(repository.root, index_root)
    assert not location.exists()
    assert not tuple(location.parent.glob("index-*.sqlite3"))


def test_failed_integrity_check_rejects_existing_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    RepositoryIndexBuilder(repository, index_root).build()
    location = index_path(repository.root, index_root)
    monkeypatch.setattr(
        "lexiforge.index.repository_index.sqlite_integrity_errors",
        lambda _: ("freelist corruption",),
    )
    with pytest.raises(IndexCorruptionError, match="freelist corruption"):
        RepositoryIndex.open(repository, location)


def test_fallback_after_corruption_matches_missing_index(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    args = [
        "candidates",
        "list",
        "--language",
        "nb",
        "--search",
        "BJØRN",
        "--data-root",
        str(repository.root),
        "--index-root",
        str(index_root),
    ]
    missing = runner.invoke(app, args)
    assert missing.exit_code == 0
    RepositoryIndexBuilder(repository, index_root).build()
    location = index_path(repository.root, index_root)
    location.write_bytes(b"corrupt")
    corrupt = runner.invoke(app, args)
    assert corrupt.exit_code == 0
    assert corrupt.stdout == missing.stdout
    assert corrupt.exception is None


def test_fallback_after_fingerprint_mismatch_matches_canonical(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    args = [
        "candidates",
        "list",
        "--language",
        "nb",
        "--data-root",
        str(repository.root),
        "--index-root",
        str(index_root),
    ]
    canonical = runner.invoke(app, args)
    assert canonical.exit_code == 0
    RepositoryIndexBuilder(repository, index_root).build()
    path = repository.root / "languages/nb/candidates.csv"
    path.write_bytes(path.read_bytes() + b"\n")
    stale = runner.invoke(app, args)
    assert stale.exit_code == 0
    assert stale.stdout == canonical.stdout
    assert stale.exception is None


def test_fallback_after_version_mismatch_and_lock_failure(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    args = [
        "candidates",
        "list",
        "--language",
        "nb",
        "--data-root",
        str(repository.root),
        "--index-root",
        str(index_root),
    ]
    canonical = runner.invoke(app, args)
    assert canonical.exit_code == 0

    builder = RepositoryIndexBuilder(repository, index_root)
    builder.build()
    location = index_path(repository.root, index_root)
    connection = sqlite3.connect(location)
    metadata = connection.execute("SELECT value FROM metadata WHERE key='metadata'").fetchone()
    assert metadata is not None
    payload = metadata[0].replace('"format_version": 1', '"format_version": 999')
    connection.execute(
        "UPDATE metadata SET value=? WHERE key='metadata'",
        (payload,),
    )
    connection.commit()
    connection.close()
    mismatch = runner.invoke(app, args)
    assert mismatch.exit_code == 0
    assert mismatch.stdout == canonical.stdout

    location.unlink()
    lock = location.with_suffix(location.suffix + ".lock")
    lock.write_text(f"pid={os.getpid()}\n", encoding="ascii")
    locked = runner.invoke(app, args)
    assert locked.exit_code == 0
    assert locked.stdout == canonical.stdout


def test_lock_conflict_abandoned_lock_and_long_running_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    location = tmp_path / "index.sqlite3"
    lock = location.with_suffix(".sqlite3.lock")
    lock.write_text(f"pid={os.getpid()}\n", encoding="ascii")
    os.utime(lock, (0, 0))
    with pytest.raises(IndexLockError), build_lock(location):
        pass
    assert lock.exists()

    lock.write_text("pid=42424242\n", encoding="ascii")
    monkeypatch.setattr("lexiforge.index.storage._process_exists", lambda _: False)
    with build_lock(location):
        assert lock.exists()
    assert not lock.exists()

    lock.write_text("owner unknown\n", encoding="ascii")
    with pytest.raises(IndexLockError), build_lock(location):
        pass
    assert lock.exists()


def test_empty_repository_builds_and_queries(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    for language in repository.load_manifest().supported_languages:
        root = repository.root / "languages" / language
        for name in ("candidates.csv", "provenance.csv", "reviews.csv"):
            path = root / name
            header = path.read_text(encoding="utf-8").splitlines()[0]
            path.write_text(header + "\n", encoding="utf-8")
    index_root = tmp_path / "index"
    metadata = RepositoryIndexBuilder(repository, index_root).build()
    assert metadata.record_counts == {"candidates": 0, "provenance": 0, "reviews": 0}
    with RepositoryIndex.open(repository, index_path(repository.root, index_root)) as index:
        assert index.search_candidates(limit=50).items == ()
        assert (
            index.get_dashboard_statistics()
            == repository_statistics(RepositorySnapshot.load(repository)).as_dict()
        )


def test_large_synthetic_repository_parity(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    _append_candidates(repository, [f"testord{number:04d}" for number in range(2_000)])
    index_root = tmp_path / "index"
    RepositoryIndexBuilder(repository, index_root).build()
    assert _indexed_candidate_ids(repository, index_root, search="TESTORD19") == (
        _canonical_candidate_ids(repository, "nb", search="TESTORD19")
    )


def test_similarity_cache_canonicalizes_pairs_and_invalidates(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    RepositoryIndexBuilder(repository, index_root).build()
    with RepositoryIndex.open(repository, index_path(repository.root, index_root)) as index:
        cache = SimilarityCache(index._connection)  # backend remains internal to this test
        key = cache_key("b", "bake", "a", "bakke", 1)
        cache.put(key, "b", "a", '{"distance": 1}')
        assert cache.get(key) is not None
        assert cache.invalidate_candidates({"a"}) == 1
        assert cache.get(key) is None


def test_index_cli_build_status_verify_and_clear(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    args = ["--data-root", str(repository.root), "--index-root", str(index_root)]
    assert runner.invoke(app, ["index", "build", *args]).exit_code == 0
    status = runner.invoke(app, ["index", "status", *args, "--format", "json"])
    assert status.exit_code == 0
    assert '"state": "valid"' in status.stdout
    assert runner.invoke(app, ["index", "verify", *args]).exit_code == 0
    assert runner.invoke(app, ["index", "clear", *args, "--yes"]).exit_code == 0
    assert not index_path(repository.root, index_root).exists()
