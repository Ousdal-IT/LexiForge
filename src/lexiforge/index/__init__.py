"""Disposable, deterministic repository indexing for read-heavy workflows."""

from .builder import RepositoryIndexBuilder
from .errors import (
    IndexBuildError,
    IndexCompatibilityError,
    IndexCorruptionError,
    IndexLockError,
    IndexNotFoundError,
    IndexStaleError,
    RepositoryIndexError,
)
from .model import IndexedCandidate, IndexMetadata, IndexQueryPage, IndexStatus
from .repository_index import RepositoryIndex
from .similarity import SimilarityCache, SimilarityCacheEntry, cache_key

__all__ = [
    "RepositoryIndex",
    "RepositoryIndexBuilder",
    "IndexMetadata",
    "IndexedCandidate",
    "IndexQueryPage",
    "IndexStatus",
    "RepositoryIndexError",
    "IndexBuildError",
    "IndexCompatibilityError",
    "IndexCorruptionError",
    "IndexLockError",
    "IndexNotFoundError",
    "IndexStaleError",
    "SimilarityCache",
    "SimilarityCacheEntry",
    "cache_key",
]
