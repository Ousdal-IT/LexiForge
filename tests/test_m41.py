import ast
import asyncio
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from textual.widgets import DataTable, Input, Select, Static

from lexiforge.constants import DEFAULT_DATA_ROOT
from lexiforge.editorial.operations import EditCandidateOperation
from lexiforge.index import RepositoryIndexBuilder
from lexiforge.models import CandidateStatus
from lexiforge.repository import DatasetRepository
from lexiforge.workbench import (
    CandidateFilter,
    CandidateQuery,
    CanonicalWorkbenchView,
    EditorialWorkbench,
    IndexedWorkbenchView,
    open_workbench_view,
)


def repository_copy(tmp_path: Path) -> DatasetRepository:
    root = tmp_path / "data"
    shutil.copytree(DEFAULT_DATA_ROOT, root)
    return DatasetRepository(root)


def backends(
    tmp_path: Path,
) -> tuple[CanonicalWorkbenchView, IndexedWorkbenchView]:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    RepositoryIndexBuilder(repository, index_root).build()
    canonical = CanonicalWorkbenchView(repository)
    indexed = open_workbench_view(repository, index_root)
    assert isinstance(indexed, IndexedWorkbenchView)
    return canonical, indexed


@pytest.mark.parametrize(
    "filters",
    [
        CandidateFilter(),
        CandidateFilter(search="BJØRN"),
        CandidateFilter(language="nb", category="animals"),
        CandidateFilter(status=CandidateStatus.APPROVED),
        CandidateFilter(review_state="pending"),
        CandidateFilter(review_state="complete"),
        CandidateFilter(release_eligible=True),
        CandidateFilter(contributor=None),
        CandidateFilter(reviewer="maintainer:example"),
        CandidateFilter(source_type="manual"),
        CandidateFilter(license_eligible=True),
        CandidateFilter(blocklist_state="clear"),
        CandidateFilter(created_after=datetime(2020, 1, 1, tzinfo=UTC)),
        CandidateFilter(modified_before=datetime(2030, 1, 1, tzinfo=UTC)),
        CandidateFilter(similarity_warning=False),
    ],
)
def test_indexed_and_canonical_filter_parity(tmp_path: Path, filters: CandidateFilter) -> None:
    canonical, indexed = backends(tmp_path)
    try:
        query = CandidateQuery(filters=filters, limit=50)
        assert indexed.list_candidates(query) == canonical.list_candidates(query)
    finally:
        canonical.close()
        indexed.close()


@pytest.mark.parametrize("sort", ["word", "language", "category", "status", "eligible"])
@pytest.mark.parametrize("reverse", [False, True])
def test_indexed_and_canonical_sort_and_page_parity(
    tmp_path: Path, sort: str, reverse: bool
) -> None:
    canonical, indexed = backends(tmp_path)
    try:
        first = CandidateQuery(sort=sort, reverse=reverse, limit=17)  # type: ignore[arg-type]
        second = CandidateQuery(
            sort=sort,
            reverse=reverse,
            offset=17,
            limit=17,  # type: ignore[arg-type]
        )
        assert indexed.list_candidates(first) == canonical.list_candidates(first)
        assert indexed.list_candidates(second) == canonical.list_candidates(second)
        assert indexed.list_candidates(first).has_next
        assert indexed.list_candidates(second).has_previous
    finally:
        canonical.close()
        indexed.close()


def test_backend_models_details_statistics_duplicates_and_similarity_match(
    tmp_path: Path,
) -> None:
    canonical, indexed = backends(tmp_path)
    candidate_id = "10000000-0000-4000-8000-000000000001"
    try:
        assert indexed.get_candidate(candidate_id) == canonical.get_candidate(candidate_id)
        assert indexed.get_dashboard_statistics() == canonical.get_dashboard_statistics()
        details = canonical.get_candidate(candidate_id)
        assert details is not None
        assert indexed.find_duplicates(
            details.candidate.language, details.normalized_word
        ) == canonical.find_duplicates(details.candidate.language, details.normalized_word)
        assert indexed.find_similarity_candidates(
            candidate_id
        ) == canonical.find_similarity_candidates(candidate_id)
        page = indexed.list_candidates(CandidateQuery(limit=5))
        assert not any(type(item).__module__.startswith("sqlite3") for item in page.items)
    finally:
        canonical.close()
        indexed.close()


def test_backend_selection_valid_missing_stale_and_corrupt(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    missing = open_workbench_view(repository, index_root)
    assert isinstance(missing, CanonicalWorkbenchView)
    assert missing.status.index_state == "missing"
    missing.close()

    RepositoryIndexBuilder(repository, index_root).build()
    valid = open_workbench_view(repository, index_root)
    assert isinstance(valid, IndexedWorkbenchView)
    valid.close()

    candidates = repository.root / "languages/nb/candidates.csv"
    candidates.write_bytes(candidates.read_bytes() + b"\n")
    stale = open_workbench_view(repository, index_root)
    assert isinstance(stale, CanonicalWorkbenchView)
    assert stale.status.index_state == "stale"
    stale.close()

    RepositoryIndexBuilder(repository, index_root).build()
    location = RepositoryIndexBuilder(repository, index_root).path
    location.write_bytes(b"corrupt")
    corrupt = open_workbench_view(repository, index_root)
    assert isinstance(corrupt, CanonicalWorkbenchView)
    assert corrupt.status.index_state == "invalid"
    corrupt.close()


def test_workbench_pagination_filter_reset_and_backend_status(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    RepositoryIndexBuilder(repository, index_root).build()

    async def scenario() -> None:
        application = EditorialWorkbench(repository, index_root)
        async with application.run_test(size=(140, 45)) as pilot:
            assert application.view.status.kind == "indexed"
            assert application.query_one("#candidate-table", DataTable).row_count == 50
            application.action_next_page()
            assert application._page.page_number == 2
            assert application.query_one("#candidate-table", DataTable).row_count == 22
            application.query_one("#search", Input).value = "bjørn"
            await pilot.pause()
            assert application._page.page_number == 1
            assert application._page.total_count == 1
            status = str(application.query_one("#status-bar", Static).render())
            assert "backend=Indexed" in status
            assert "page=1/1" in status

    asyncio.run(scenario())


def test_workbench_missing_index_uses_fallback(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)

    async def scenario() -> None:
        application = EditorialWorkbench(repository, tmp_path / "missing-index")
        async with application.run_test(size=(140, 45)) as pilot:
            assert application.view.status.kind == "canonical"
            assert application._page.total_count == 72
            assert "Canonical fallback" in str(
                application.query_one("#status-bar", Static).render()
            )
            application.action_build_index()
            await application.workers.wait_for_complete()
            await pilot.pause()
            assert application.view.status.kind == "indexed"

    asyncio.run(scenario())


def test_workbench_architecture_has_no_sqlite_or_csv_writes() -> None:
    root = Path(__file__).parents[1] / "src/lexiforge/workbench"
    app_tree = ast.parse((root / "app.py").read_text(encoding="utf-8"))
    query_tree = ast.parse((root / "query.py").read_text(encoding="utf-8"))
    imports = {
        alias.name
        for tree in (app_tree, query_tree)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "sqlite3" not in imports
    calls = {
        node.func.attr
        for node in ast.walk(app_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not {"write_text", "write_bytes", "open"} & calls
    assert "apply" in calls


def test_session_pagination_remains_backend_independent(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    application = EditorialWorkbench(repository, tmp_path / "index")
    assert not hasattr(application._persisted, "index_path")
    assert application._persisted.page_offset == 0


def test_filter_change_resets_select_page_without_sleep(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)

    async def scenario() -> None:
        application = EditorialWorkbench(repository, tmp_path / "index")
        async with application.run_test(size=(140, 45)) as pilot:
            application.action_next_page()
            language = application.query_one("#language-filter", Select)
            language.value = "nn"
            for _ in range(5):
                await pilot.pause()
                if application._page.page_number == 1:
                    break
            assert application._page.page_number == 1
            assert {item.candidate.language for item in application._visible} == {"nn"}

    asyncio.run(scenario())


def test_successful_mutation_switches_to_canonical_and_rebuilds(
    tmp_path: Path,
) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    RepositoryIndexBuilder(repository, index_root).build()

    async def scenario() -> None:
        application = EditorialWorkbench(repository, index_root)
        async with application.run_test(size=(140, 45)) as pilot:
            assert application.view.status.kind == "indexed"
            change = application.service.preview(
                EditCandidateOperation(
                    candidate_id="10000000-0000-4000-8000-000000000005",
                    notes="M4.1 mutation",
                )
            )
            application.pending_changeset = change
            application.action_apply()
            assert application.view.status.kind == "canonical"
            assert application.view.status.index_state == "stale"
            await application.workers.wait_for_complete()
            await pilot.pause()
            assert application.view.status.kind == "indexed"
            assert application.selected_candidate() is not None

    asyncio.run(scenario())


def test_successful_mutation_survives_failed_index_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = repository_copy(tmp_path)
    index_root = tmp_path / "index"
    RepositoryIndexBuilder(repository, index_root).build()

    def fail_build(self: object, progress: object = None) -> None:
        raise RuntimeError("synthetic index failure")

    monkeypatch.setattr("lexiforge.workbench.app.RepositoryIndexBuilder.build", fail_build)

    async def scenario() -> None:
        application = EditorialWorkbench(repository, index_root)
        async with application.run_test(size=(140, 45)) as pilot:
            application.pending_changeset = application.service.preview(
                EditCandidateOperation(
                    candidate_id="10000000-0000-4000-8000-000000000005",
                    notes="M4.1 failed rebuild",
                )
            )
            application.action_apply()
            await application.workers.wait_for_complete()
            await pilot.pause()
            assert application.view.status.kind == "canonical"
            assert application._index_build_state == "failed"
            assert (
                "M4.1 failed rebuild"
                in application.service.candidate("10000000-0000-4000-8000-000000000005").notes
            )

    asyncio.run(scenario())
