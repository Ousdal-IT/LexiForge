import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, content: str) -> None:
    """Replace one UTF-8 text file atomically after fully staging its content."""
    if content and not content.endswith("\n"):
        raise ValueError("atomic text writes require a final newline")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
