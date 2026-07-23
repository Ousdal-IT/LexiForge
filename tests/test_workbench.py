import asyncio
import shutil
from pathlib import Path

from textual.widgets import Button, Checkbox, DataTable, Input, Select, Static
from typer.testing import CliRunner

from lexiforge.cli import app as cli_app
from lexiforge.constants import DEFAULT_DATA_ROOT
from lexiforge.editorial import EditorialService
from lexiforge.repository import DatasetRepository
from lexiforge.workbench import CandidateFilter, EditorialWorkbench, RepositorySnapshot
from lexiforge.workbench.screens import (
    AddCandidateScreen,
    EditCandidateScreen,
    HelpScreen,
    ProvenanceScreen,
    ReviewScreen,
)

runner = CliRunner()


def repository_copy(tmp_path: Path) -> DatasetRepository:
    root = tmp_path / "external-data"
    shutil.copytree(DEFAULT_DATA_ROOT, root)
    return DatasetRepository(root)


def snapshot_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_snapshot_supports_search_and_all_filters() -> None:
    snapshot = RepositorySnapshot.load(DatasetRepository(DEFAULT_DATA_ROOT))
    candidate = snapshot.candidates[0]
    assert snapshot.filtered(CandidateFilter(search=candidate.candidate.id)) == (candidate,)
    assert candidate in snapshot.filtered(CandidateFilter(search=candidate.normalized_word))
    assert all(
        item.candidate.language == "nb"
        for item in snapshot.filtered(CandidateFilter(language="nb"))
    )
    assert all(
        item.release_eligible for item in snapshot.filtered(CandidateFilter(release_eligible=True))
    )
    assert all(
        item.candidate.status.value == "approved"
        for item in snapshot.filtered(CandidateFilter(status=candidate.candidate.status))
        if candidate.candidate.status.value == "approved"
    )


def test_service_candidate_lookup_supports_uuid_and_exact_word() -> None:
    service = EditorialService(DatasetRepository(DEFAULT_DATA_ROOT))
    by_id = service.lookup_candidate("10000000-0000-4000-8000-000000000001")
    by_word = service.lookup_candidate("bjørn", "nb")
    assert by_id == by_word


def test_workbench_renders_browser_details_and_status() -> None:
    async def scenario() -> None:
        application = EditorialWorkbench(DatasetRepository(DEFAULT_DATA_ROOT))
        async with application.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            table = application.query_one("#candidate-table", DataTable)
            assert table.row_count == len(application.snapshot.candidates)
            assert application.selected_id is not None
            assert "UUID:" in str(application.query_one("#candidate-details", Static).render())
            status = str(application.query_one("#status-bar", Static).render())
            assert str(DEFAULT_DATA_ROOT.resolve()) in status
            assert "clean" in status

    asyncio.run(scenario())


def test_search_and_filter_update_candidate_table() -> None:
    async def scenario() -> None:
        application = EditorialWorkbench(DatasetRepository(DEFAULT_DATA_ROOT))
        async with application.run_test(size=(140, 45)) as pilot:
            search = application.query_one("#search", Input)
            search.value = "bjørn"
            await pilot.pause()
            assert application.query_one("#candidate-table", DataTable).row_count == 1
            assert application._visible[0].candidate.word == "bjørn"
            search.value = ""
            language = application.query_one("#language-filter", Select)
            language.value = "nn"
            await pilot.pause()
            assert application._visible
            assert {item.candidate.language for item in application._visible} == {"nn"}

    asyncio.run(scenario())


def test_keyboard_navigation_opens_and_cancels_screens() -> None:
    async def scenario() -> None:
        application = EditorialWorkbench(DatasetRepository(DEFAULT_DATA_ROOT))
        async with application.run_test(size=(140, 45)) as pilot:
            await pilot.press("a")
            assert isinstance(application.screen, AddCandidateScreen)
            await pilot.press("escape")
            await pilot.press("e")
            assert isinstance(application.screen, EditCandidateScreen)
            await pilot.press("escape")
            await pilot.press("r")
            assert isinstance(application.screen, ReviewScreen)
            await pilot.press("escape")
            await pilot.press("p")
            assert isinstance(application.screen, ProvenanceScreen)
            await pilot.press("escape")
            await pilot.press("f1")
            assert isinstance(application.screen, HelpScreen)
            await pilot.press("escape")

    asyncio.run(scenario())


def test_edit_preview_uses_existing_renderer_and_does_not_write(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    before = snapshot_files(repository.root)

    async def scenario() -> None:
        application = EditorialWorkbench(repository)
        async with application.run_test(size=(140, 45)) as pilot:
            item = application.snapshot.candidate("10000000-0000-4000-8000-000000000005")
            assert item is not None
            application.select_candidate(item)
            application.action_edit()
            await pilot.pause()
            screen = application.screen
            assert isinstance(screen, EditCandidateScreen)
            screen.query_one("#note", Input).value = "Workbench preview note."
            screen.query_one("#preview", Button).press()
            await pilot.pause()
            assert application.pending_changeset is not None
            preview = str(application.query_one("#preview", Static).render())
            assert "Operation: candidate.edit" in preview
            assert "Field changes:" in preview

    asyncio.run(scenario())
    assert snapshot_files(repository.root) == before


def test_ctrl_a_applies_exact_pending_changeset_to_external_repository(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    candidate_id = "10000000-0000-4000-8000-000000000005"

    async def scenario() -> None:
        application = EditorialWorkbench(repository)
        async with application.run_test(size=(140, 45)) as pilot:
            item = application.snapshot.candidate(candidate_id)
            assert item is not None
            application.select_candidate(item)
            application.action_edit()
            await pilot.pause()
            screen = application.screen
            assert isinstance(screen, EditCandidateScreen)
            screen.query_one("#note", Input).value = "Applied from workbench."
            screen.query_one("#preview", Button).press()
            await pilot.pause()
            pending = application.pending_changeset
            assert pending is not None
            await pilot.press("ctrl+a")
            await pilot.pause()
            assert application.pending_changeset is None
            assert "Applied candidate.edit" in str(
                application.query_one("#preview", Static).render()
            )

    asyncio.run(scenario())
    assert EditorialService(repository).candidate(candidate_id).notes == "Applied from workbench."
    assert repository.validate_layout() == []


def test_add_form_builds_service_validated_preview(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)

    async def scenario() -> None:
        application = EditorialWorkbench(repository)
        async with application.run_test(size=(140, 50)) as pilot:
            application.action_add()
            await pilot.pause()
            screen = application.screen
            assert isinstance(screen, AddCandidateScreen)
            screen.query_one("#word", Input).value = "soloppgang"
            screen.query_one("#category", Input).value = "nature"
            screen.query_one("#submitter", Input).value = "editor-pgo"
            screen.query_one("#source-reference", Input).value = "workbench-test"
            screen.query_one("#license-basis", Input).value = "contributor-assertion"
            screen.query_one("#license-eligible", Checkbox).value = True
            screen.query_one("#created-at", Input).value = "2026-07-23T12:00:00+02:00"
            screen.query_one("#preview", Button).press()
            await pilot.pause()
            assert application.pending_changeset is not None
            assert application.pending_changeset.operation == "candidate.add"

    before = snapshot_files(repository.root)
    asyncio.run(scenario())
    assert snapshot_files(repository.root) == before


def test_editor_cli_resolves_external_repository_without_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    repository = repository_copy(tmp_path)
    before = snapshot_files(repository.root)
    launched: list[Path] = []

    def fake_run(self: EditorialWorkbench) -> None:
        launched.append(self.repository.root)

    monkeypatch.setattr(EditorialWorkbench, "run", fake_run)
    result = runner.invoke(cli_app, ["editor", "--data-root", str(repository.root)])
    assert result.exit_code == 0
    assert launched == [repository.root]
    assert snapshot_files(repository.root) == before


def test_editor_help_is_available() -> None:
    result = runner.invoke(cli_app, ["editor", "--help"])
    assert result.exit_code == 0
    assert "service-backed editorial workbench" in result.stdout
