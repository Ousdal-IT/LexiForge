import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lexiforge.cli import app
from lexiforge.constants import DEFAULT_DATA_ROOT
from lexiforge.index import (
    IndexStaleError,
    RepositoryIndex,
    RepositoryIndexBuilder,
    SimilarityCache,
    cache_key,
)
from lexiforge.index.storage import index_path
from lexiforge.repository import DatasetRepository

runner = CliRunner()


def repository_copy(tmp_path: Path) -> DatasetRepository:
    root = tmp_path / "data"
    shutil.copytree(DEFAULT_DATA_ROOT, root)
    return DatasetRepository(root)


def test_full_index_build_and_query_parity(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    metadata = RepositoryIndexBuilder(repository, index_root).build()
    assert metadata.record_counts == {"candidates": 72, "provenance": 72, "reviews": 48}
    with RepositoryIndex.open(repository, index_path(repository.root, index_root)) as index:
        assert index.count_candidates() == 72
        assert index.get_candidate("10000000-0000-4000-8000-000000000001") is not None
        assert index.find_by_normalized_word("nb", "bjørn")[0].candidate.word == "bjørn"
        page = index.search_candidates("b", language="nb", limit=3)
        assert page.items == tuple(
            sorted(page.items, key=lambda item: (item.normalized_word, item.candidate.id))
        )
        assert index.get_provenance("10000000-0000-4000-8000-000000000001")
        assert index.get_reviews("10000000-0000-4000-8000-000000000001")
        assert index.get_dashboard_statistics()["total_candidates"] == 72


def test_stale_index_is_rejected_and_refresh_rebuilds(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    RepositoryIndexBuilder(repository, index_root).build()
    candidate_path = repository.root / "languages/nb/candidates.csv"
    candidate_path.write_bytes(
        candidate_path.read_bytes().replace(b"bj\xc3\xb8rn", b"bj\xc3\xb8rn")
    )
    candidate_path.write_text(candidate_path.read_text(encoding="utf-8") + "", encoding="utf-8")
    # A content change is enough to invalidate the fingerprint without changing semantics.
    candidate_path.write_bytes(candidate_path.read_bytes() + b"\n")
    with pytest.raises(IndexStaleError):
        RepositoryIndex.open(repository, index_path(repository.root, index_root))
    metadata, strategy = RepositoryIndexBuilder(repository, index_root).refresh()
    assert strategy == "full_rebuild"
    assert metadata.completed


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
