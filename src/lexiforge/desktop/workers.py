"""Small Qt-native worker helpers with request/generation protection."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class Worker(QRunnable):
    def __init__(self, function: Callable[[], Any]) -> None:
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.finished.emit(self.function())
        except Exception as error:  # worker boundary: surface structured text to UI
            self.signals.failed.emit(str(error))


def submit(function: Callable[[], Any]) -> Worker:
    """Construct a worker; callers connect and retain it before starting it."""
    return Worker(function)
