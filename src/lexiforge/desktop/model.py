"""Qt models for the native desktop workbench.

This module is intentionally a thin presentation adapter: repository reads are
performed by ``WorkbenchRepositoryView`` and only one bounded page is retained.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)

from ..workbench.query import CandidatePage

_DEFAULT_INDEX = QModelIndex()


class CandidateTableModel(QAbstractTableModel):
    headers = ("Word", "Language", "Category", "Status", "Eligible")

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._page = CandidatePage((), 0, 0, 50)

    @property
    def page(self) -> CandidatePage:
        return self._page

    def set_page(self, page: CandidatePage) -> None:
        self.beginResetModel()
        self._page = page
        self.endResetModel()

    def candidate_id(self, row: int) -> str | None:
        if 0 <= row < len(self._page.items):
            return self._page.items[row].candidate.id
        return None

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex | None = _DEFAULT_INDEX) -> int:
        return 0 if parent is not None and parent.isValid() else len(self._page.items)

    def columnCount(
        self, parent: QModelIndex | QPersistentModelIndex | None = _DEFAULT_INDEX
    ) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.headers)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object | None:
        if not index.isValid() or not (0 <= index.row() < len(self._page.items)):
            return None
        item = self._page.items[index.row()]
        values = (
            item.candidate.word,
            item.candidate.language,
            item.candidate.category or "",
            item.candidate.status.value,
            "yes" if item.release_eligible else "no",
        )
        if role == Qt.ItemDataRole.DisplayRole:
            return values[index.column()]
        if role == Qt.ItemDataRole.UserRole and index.column() == 0:
            return item.candidate.id
        if role == Qt.ItemDataRole.ToolTipRole:
            return item.candidate.id
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object | None:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.headers):
            return self.headers[section]
        return str(section + 1) if orientation == Qt.Orientation.Vertical else None
