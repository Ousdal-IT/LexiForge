import ast
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from typer.testing import CliRunner

from lexiforge.cli import app
from lexiforge.constants import DEFAULT_DATA_ROOT
from lexiforge.desktop.session import DesktopSession
from lexiforge.index import RepositoryIndexBuilder
from lexiforge.repository import DatasetRepository
from lexiforge.workbench import CandidateQuery, IndexedWorkbenchView, open_workbench_view

runner = CliRunner()


def test_desktop_command_is_exposed_without_importing_qt() -> None:
    result = runner.invoke(app, ["desktop", "--help"])
    assert result.exit_code == 0
    assert "native PySide6 desktop workbench" in result.stdout


def test_desktop_command_reports_missing_optional_dependency(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "PySide6", None)
    monkeypatch.setitem(sys.modules, "PySide6.QtWidgets", None)
    result = runner.invoke(app, ["desktop"])
    assert result.exit_code == 2
    assert "PySide6 is required" in result.stderr
    assert "uv sync --extra desktop" in result.stderr
    assert result.exception is not None


def test_desktop_session_is_external_deterministic_and_bounded(tmp_path: Path) -> None:
    path = tmp_path / "config/desktop.json"
    session = DesktopSession(path)
    for number in range(12):
        session.remember(tmp_path / f"repository-{number}")
    session.data["geometry"] = "00ff"
    session.save()

    payload = path.read_text(encoding="utf-8")
    assert payload.endswith("\n")
    assert list(json.loads(payload)) == ["geometry", "recent_repositories"]
    restored = DesktopSession(path)
    assert len(restored.recent()) == 10
    assert restored.recent()[0].endswith("repository-11")


def test_desktop_session_ignores_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "desktop.json"
    path.write_text("{invalid", encoding="utf-8")
    assert DesktopSession(path).data == {}


def test_desktop_presentation_has_no_dataset_or_sqlite_writes() -> None:
    root = Path(__file__).parents[1] / "src/lexiforge/desktop"
    trees = [
        ast.parse(path.read_text(encoding="utf-8"))
        for path in root.glob("*.py")
        if path.name != "session.py"
    ]
    imports = {
        alias.name
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    calls = {
        node.func.attr
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "sqlite3" not in imports
    assert not {"write_text", "write_bytes"} & calls


def test_indexed_desktop_view_can_query_from_worker_thread(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    shutil.copytree(DEFAULT_DATA_ROOT, data_root)
    repository = DatasetRepository(data_root)
    index_root = tmp_path / "index"
    RepositoryIndexBuilder(repository, index_root).build()
    view = open_workbench_view(repository, index_root, cross_thread=True)
    assert isinstance(view, IndexedWorkbenchView)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            page = executor.submit(view.list_candidates, CandidateQuery(limit=5)).result()
        assert len(page.items) == 5
        assert page.total_count > len(page.items)
    finally:
        view.close()
