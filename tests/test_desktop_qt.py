import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFileDialog

from lexiforge.constants import DEFAULT_DATA_ROOT
from lexiforge.desktop.main_window import DesktopMainWindow
from lexiforge.desktop.session import DesktopSession
from lexiforge.index import RepositoryIndexBuilder
from lexiforge.repository import DatasetRepository


def _wait_for(application: QApplication, predicate: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 10
    while not predicate() and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.01)
    assert predicate()


def _repository_copy(tmp_path: Path, name: str) -> DatasetRepository:
    root = tmp_path / name
    shutil.copytree(DEFAULT_DATA_ROOT, root)
    return DatasetRepository(root)


def test_desktop_indexed_search_repository_switch_and_clean_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = QApplication.instance() or QApplication([])
    index_root = tmp_path / "indexes"
    monkeypatch.setenv("LEXIFORGE_INDEX_ROOT", str(index_root))
    first = _repository_copy(tmp_path, "first")
    second = _repository_copy(tmp_path, "second")
    RepositoryIndexBuilder(first).build()
    RepositoryIndexBuilder(second).build()
    window = DesktopMainWindow(first, session=DesktopSession(tmp_path / "session.json"))
    window.show()
    try:
        _wait_for(application, lambda: window.model.page.total_count > 0)
        assert window.view.status.kind == "indexed"
        assert len(window.model.page.items) == window.PAGE_SIZE
        assert window.next.isEnabled()

        window._page(1)
        assert not window.previous.isEnabled()
        assert not window.next.isEnabled()
        _wait_for(application, lambda: window.model.page.page_number == 2)

        window.search.setText("bjørn")
        assert not window.next.isEnabled()
        _wait_for(application, lambda: window.model.page.total_count == 1)
        assert window.model.page.items[0].candidate.word == "bjørn"

        monkeypatch.setattr(
            QFileDialog, "getExistingDirectory", lambda *_args, **_kwargs: str(second.root)
        )
        window.open_repository()
        _wait_for(
            application,
            lambda: window.repository.root == second.root and window.model.page.total_count == 1,
        )
        assert window.view.status.kind == "indexed"

        window.table.selectRow(0)
        _wait_for(application, lambda: window.overview.toPlainText().startswith("bjørn"))
        window.search.setText("no-such-candidate")
        _wait_for(application, lambda: window.model.page.total_count == 0)
        assert window.overview.toPlainText() == "Select a candidate to view details."
        assert not window.reviews.toPlainText()
        assert not window.provenance.toPlainText()
    finally:
        window.close()
        application.processEvents()
    assert not window.workers


def test_desktop_repository_switch_preserves_canonical_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = QApplication.instance() or QApplication([])
    first = _repository_copy(tmp_path, "first")
    second = _repository_copy(tmp_path, "second")
    window = DesktopMainWindow(
        first,
        canonical_only=True,
        session=DesktopSession(tmp_path / "session.json"),
    )
    try:
        monkeypatch.setattr(
            QFileDialog, "getExistingDirectory", lambda *_args, **_kwargs: str(second.root)
        )
        window.open_repository()
        _wait_for(application, lambda: window.repository.root == second.root)
        assert window.view.status.kind == "canonical"
        assert window.view.status.index_state == "disabled"
    finally:
        window.close()
        application.processEvents()
