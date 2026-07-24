"""Native Qt presentation for the existing workbench query and service layers."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableView,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..repository import DatasetRepository
from ..workbench.model import CandidateFilter
from ..workbench.query import (
    CandidateQuery,
    CanonicalWorkbenchView,
    WorkbenchRepositoryView,
    open_workbench_view,
)
from .model import CandidateTableModel
from .session import DesktopSession
from .workers import submit


class ChangePreviewDialog(QDialog):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ChangeSet preview")
        layout = QVBoxLayout(self)
        editor = QTextEdit(self)
        editor.setReadOnly(True)
        editor.setPlainText(text)
        editor.setAccessibleName("ChangeSet preview")
        layout.addWidget(editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class DesktopMainWindow(QMainWindow):
    PAGE_SIZE = 50

    def __init__(
        self,
        repository: DatasetRepository,
        *,
        canonical_only: bool = False,
        session: DesktopSession | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.session = session or DesktopSession()
        self.canonical_only = canonical_only
        self.generation = 0
        self.page_request_id = 0
        self.detail_request_id = 0
        self.worker_pool = QThreadPool(self)
        self.worker_pool.setMaxThreadCount(1)
        self.workers: set[Any] = set()
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.refresh)
        self.view: WorkbenchRepositoryView = (
            CanonicalWorkbenchView(repository, index_state="disabled", reason="--canonical")
            if canonical_only
            else open_workbench_view(repository, cross_thread=True)
        )
        self.query = CandidateQuery(limit=self.PAGE_SIZE)
        self.setWindowTitle("LexiForge Desktop Workbench")
        self.setMinimumSize(1000, 650)
        self._build_ui()
        self._build_actions()
        self._restore_state()
        self.refresh()

    def _build_ui(self) -> None:
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search candidates…")
        self.search.setAccessibleName("Candidate search")
        self.search.textChanged.connect(self._search_changed)
        self.language = QComboBox()
        self.language.setAccessibleName("Language filter")
        self.language.addItem("All languages", None)
        for value in self.view.languages:
            self.language.addItem(value, value)
        self.language.currentIndexChanged.connect(self._filter_changed)
        self.category = QComboBox()
        self.category.setAccessibleName("Category filter")
        self.category.addItem("All categories", None)
        for value in self.view.categories:
            self.category.addItem(value, value)
        self.category.currentIndexChanged.connect(self._filter_changed)
        toolbar = QToolBar("Query")
        toolbar.addWidget(QLabel("Search"))
        toolbar.addWidget(self.search)
        toolbar.addWidget(self.language)
        toolbar.addWidget(self.category)
        self.addToolBar(toolbar)

        self.table = QTableView()
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.model = CandidateTableModel(self.table)
        self.table.setModel(self.model)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.details = QTabWidget()
        self.overview = QTextEdit()
        self.overview.setReadOnly(True)
        self.reviews = QTextEdit()
        self.reviews.setReadOnly(True)
        self.provenance = QTextEdit()
        self.provenance.setReadOnly(True)
        self.details.addTab(self.overview, "Overview")
        self.details.addTab(self.reviews, "Reviews")
        self.details.addTab(self.provenance, "Provenance")
        self._clear_details()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.table)
        splitter.addWidget(self.details)
        splitter.setSizes([600, 400])
        self.page_label = QLabel()
        self.previous = QPushButton("Previous")
        self.previous.clicked.connect(lambda: self._page(-1))
        self.next = QPushButton("Next")
        self.next.clicked.connect(lambda: self._page(1))
        footer = QWidget()
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(4, 2, 4, 2)
        footer_layout.addWidget(self.page_label)
        footer_layout.addWidget(self.previous)
        footer_layout.addWidget(self.next)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(splitter)
        layout.addWidget(footer)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar(self))
        self._update_status()

    def _build_actions(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        open_action = QAction("Open Repository", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_repository)
        file_menu.addAction(open_action)
        reload_action = QAction("Reload", self)
        reload_action.setShortcut(QKeySequence.StandardKey.Refresh)
        reload_action.triggered.connect(self.refresh)
        file_menu.addAction(reload_action)
        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        view_menu = self.menuBar().addMenu("View")
        reset = QAction("Reset Layout", self)
        reset.triggered.connect(self._reset_layout)
        view_menu.addAction(reset)
        help_menu = self.menuBar().addMenu("Help")
        shortcuts = QAction("Keyboard Shortcuts", self)
        shortcuts.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts)
        self.search_action = QAction("Focus Search", self)
        self.search_action.setShortcut(QKeySequence("Ctrl+F"))
        self.search_action.triggered.connect(self.search.setFocus)
        self.addAction(self.search_action)

    def _filters(self) -> CandidateFilter:
        return CandidateFilter(
            search=self.search.text(),
            language=self.language.currentData(),
            category=self.category.currentData(),
        )

    def refresh(self) -> None:
        self.page_request_id += 1
        request = self.page_request_id
        generation = self.generation
        query = replace(self.query, filters=self._filters())
        self.previous.setEnabled(False)
        self.next.setEnabled(False)
        self._start_worker(
            lambda: self.view.list_candidates(query),
            lambda page: self._page_ready(page, request, generation),
            lambda message: self._page_error(message, request, generation),
        )

    def _page_ready(self, page: Any, request: int, generation: int) -> None:
        if request != self.page_request_id or generation != self.generation:
            return
        self.query = replace(self.query, offset=page.offset, filters=self._filters())
        self.model.set_page(page)
        self.page_label.setText(
            f"Page {page.page_number} of {page.page_count} · {page.total_count} matches"
        )
        self.previous.setEnabled(page.has_previous)
        self.next.setEnabled(page.has_next)
        self._update_status()

    def _search_changed(self, _: str) -> None:
        self.query = replace(self.query, offset=0)
        self.page_request_id += 1
        self.previous.setEnabled(False)
        self.next.setEnabled(False)
        self._clear_details()
        self.search_timer.start(180)

    def _filter_changed(self, _: int) -> None:
        self.query = replace(self.query, offset=0)
        self.refresh()

    def _page(self, direction: int) -> None:
        self.query = replace(
            self.query, offset=max(0, self.query.offset + direction * self.PAGE_SIZE)
        )
        self.refresh()

    def _selection_changed(self, *_: object) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self._clear_details()
            return
        candidate_id = self.model.candidate_id(rows[0].row())
        if candidate_id is None:
            return
        self.detail_request_id += 1
        request = self.detail_request_id
        generation = self.generation
        self._start_worker(
            lambda: self.view.get_candidate(candidate_id),
            lambda item: self._detail_ready(item, request, generation),
            lambda message: self._detail_error(message, request, generation),
        )

    def _start_worker(self, function: Any, finished: Any, failed: Any) -> None:
        worker = submit(function)
        self.workers.add(worker)
        worker.signals.finished.connect(finished)
        worker.signals.failed.connect(failed)
        worker.signals.finished.connect(lambda _: self.workers.discard(worker))
        worker.signals.failed.connect(lambda _: self.workers.discard(worker))
        self.worker_pool.start(worker)

    def _detail_ready(self, item: Any, request: int, generation: int) -> None:
        if request != self.detail_request_id or generation != self.generation:
            return
        if item is None:
            self.overview.setPlainText("Candidate is no longer present.")
            self.reviews.clear()
            self.provenance.clear()
            return
        reasons = ", ".join(item.eligibility_reasons) or "none"
        self.overview.setPlainText(
            f"{item.candidate.word}\n{item.candidate.id}\n"
            f"Language: {item.candidate.language}\n"
            f"Status: {item.candidate.status.value}\n"
            f"Eligible: {item.release_eligible}\nReasons: {reasons}"
        )
        self.reviews.setPlainText(
            "\n".join(
                f"{r.reviewed_at.isoformat()} — {r.reviewer_id}: {r.decision.value}"
                for r in item.reviews
            )
            or "No reviews"
        )
        self.provenance.setPlainText(
            "\n".join(
                f"{p.created_at.isoformat() if p.created_at else ''} — "
                f"{p.source_kind.value}: {p.source_reference or ''}"
                for p in item.provenance
            )
            or "No provenance"
        )

    def _clear_details(self) -> None:
        self.overview.setPlainText("Select a candidate to view details.")
        self.reviews.clear()
        self.provenance.clear()

    def _page_error(self, message: str, request: int, generation: int) -> None:
        if request == self.page_request_id and generation == self.generation:
            self._error(message)

    def _detail_error(self, message: str, request: int, generation: int) -> None:
        if request == self.detail_request_id and generation == self.generation:
            self._error(message)

    def _update_status(self) -> None:
        self.statusBar().showMessage(f"{self.repository.root} · {self.view.status.label}")

    def _error(self, message: str) -> None:
        QMessageBox.warning(self, "LexiForge", message)

    def open_repository(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open repository")
        if not path:
            return
        try:
            repository = DatasetRepository.resolve(Path(path))
            repository.load_manifest()
            errors = repository.validate_layout()
        except Exception as error:
            self._error(str(error))
            return
        if errors:
            self._error("Invalid repository: " + "; ".join(errors))
            return
        try:
            replacement = (
                CanonicalWorkbenchView(repository, index_state="disabled", reason="--canonical")
                if self.canonical_only
                else open_workbench_view(repository, cross_thread=True)
            )
        except Exception as error:
            self._error(str(error))
            return
        self.generation += 1
        self.page_request_id += 1
        self.detail_request_id += 1
        self.worker_pool.waitForDone()
        self.view.close()
        self.repository = repository
        self.session.remember(repository.root)
        self.view = replacement
        self._reload_filter_options()
        self.query = replace(self.query, offset=0)
        self.refresh()
        self._update_status()

    def _reload_filter_options(self) -> None:
        selected_language = self.language.currentData()
        selected_category = self.category.currentData()
        self.language.blockSignals(True)
        self.category.blockSignals(True)
        self.language.clear()
        self.language.addItem("All languages", None)
        for value in self.view.languages:
            self.language.addItem(value, value)
        self.category.clear()
        self.category.addItem("All categories", None)
        for value in self.view.categories:
            self.category.addItem(value, value)
        self.language.setCurrentIndex(max(0, self.language.findData(selected_language)))
        self.category.setCurrentIndex(max(0, self.category.findData(selected_category)))
        self.language.blockSignals(False)
        self.category.blockSignals(False)

    def _reset_layout(self) -> None:
        self.resize(1200, 750)

    def _show_shortcuts(self) -> None:
        QMessageBox.information(
            self,
            "Keyboard shortcuts",
            "Ctrl+O Open · Ctrl+F Search · Ctrl+R Reload · Esc Close dialogs",
        )

    def _restore_state(self) -> None:
        geometry = self.session.data.get("geometry")
        if isinstance(geometry, str):
            try:
                self.restoreGeometry(bytes.fromhex(geometry))
            except ValueError:
                self.session.data.pop("geometry", None)

    def closeEvent(self, event: Any) -> None:
        self.generation += 1
        self.page_request_id += 1
        self.detail_request_id += 1
        self.worker_pool.waitForDone()
        self.workers.clear()
        self.session.data["geometry"] = self.saveGeometry().data().hex()
        self.session.remember(self.repository.root)
        with suppress(OSError):
            self.session.save()
        self.view.close()
        event.accept()
