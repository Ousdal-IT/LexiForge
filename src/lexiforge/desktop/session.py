"""Backend-independent desktop presentation state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DesktopSession:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path.home() / ".config/lexiforge/desktop.json"
        self.data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            value = {}
        self.data = value if isinstance(value, dict) else {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.data, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(self.path)

    def recent(self) -> list[str]:
        values = self.data.get("recent_repositories", [])
        return [str(item) for item in values if isinstance(item, str)]

    def remember(self, root: Path) -> None:
        values = [str(root), *[item for item in self.recent() if item != str(root)]]
        self.data["recent_repositories"] = values[:10]
