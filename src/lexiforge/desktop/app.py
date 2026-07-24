"""Application bootstrap; imports Qt only when the desktop command is used."""

from __future__ import annotations

from ..repository import DatasetRepository


def run(
    repository: DatasetRepository,
    *,
    canonical_only: bool = False,
    reset_session: bool = False,
) -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as error:
        raise RuntimeError(
            "PySide6 is required for the desktop workbench; install with `uv sync --extra desktop`"
        ) from error
    from .main_window import DesktopMainWindow
    from .session import DesktopSession

    session = DesktopSession()
    if reset_session:
        session.data = {}
    application = QApplication.instance() or QApplication([])
    window = DesktopMainWindow(repository, canonical_only=canonical_only, session=session)
    window.show()
    return int(application.exec())


__all__ = ["run"]
