"""Safe index paths, hashing and local build locking."""

import hashlib
import os
import time
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


@contextmanager
def build_lock(path: Path) -> Iterator[None]:
    lock = path.with_suffix(path.suffix + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        try:
            if time.time() - lock.stat().st_mtime > 3600:
                lock.unlink(missing_ok=True)
                descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            else:
                raise IndexLockError(f"index build is already in progress: {lock}") from error
        except FileNotFoundError:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError as error:
        raise IndexLockError(f"cannot create index build lock: {lock}") from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.close(descriptor)
        yield
    finally:
        lock.unlink(missing_ok=True)
