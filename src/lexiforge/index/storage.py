"""Safe index paths, hashing and local build locking."""

import hashlib
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import IndexLockError, RepositoryIndexError


def default_index_root() -> Path:
    configured = os.environ.get("LEXIFORGE_INDEX_ROOT")
    if configured:
        return Path(configured).expanduser()
    cache = os.environ.get("XDG_CACHE_HOME")
    if cache:
        return Path(cache).expanduser() / "lexiforge/index"
    return Path.home() / ".cache/lexiforge/index"


def repository_namespace(repository_root: Path) -> str:
    return hashlib.sha256(str(repository_root.resolve()).encode("utf-8")).hexdigest()[:32]


def index_path(repository_root: Path, index_root: Path | None = None) -> Path:
    canonical = repository_root.resolve()
    root = (index_root or default_index_root()).expanduser().resolve()
    try:
        root.relative_to(canonical)
    except ValueError:
        pass
    else:
        raise RepositoryIndexError("index root must not be inside the canonical dataset repository")
    return root / repository_namespace(repository_root) / "index.sqlite3"


def content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_integrity_errors(connection: sqlite3.Connection) -> tuple[str, ...]:
    """Return integrity diagnostics; an empty tuple is the only valid result."""
    rows = connection.execute("PRAGMA integrity_check").fetchall()
    results = tuple(str(row[0]) for row in rows)
    if results == ("ok",):
        return ()
    return results or ("no result",)


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _lock_owner(lock: Path) -> int | None:
    try:
        content = lock.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    if not content.startswith("pid="):
        return None
    try:
        return int(content.removeprefix("pid="))
    except ValueError:
        return None


def _acquire_lock(lock: Path) -> int:
    try:
        return os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        owner = _lock_owner(lock)
        if owner is None or _process_exists(owner):
            raise IndexLockError(f"index build is already in progress: {lock}") from error
        try:
            lock.unlink()
            return os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except (FileExistsError, FileNotFoundError, OSError) as retry_error:
            raise IndexLockError(f"cannot replace abandoned index lock: {lock}") from retry_error
    except OSError as error:
        raise IndexLockError(f"cannot create index build lock: {lock}") from error


@contextmanager
def build_lock(path: Path) -> Iterator[None]:
    lock = path.with_suffix(path.suffix + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = _acquire_lock(lock)
    try:
        try:
            os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        finally:
            os.close(descriptor)
        yield
    finally:
        lock.unlink(missing_ok=True)
