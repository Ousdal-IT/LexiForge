"""Errors raised while reading or building the derived repository index."""


class RepositoryIndexError(Exception):
    """Base class for safe, disposable index failures."""


class IndexNotFoundError(RepositoryIndexError):
    pass


class IndexStaleError(RepositoryIndexError):
    pass


class IndexCompatibilityError(RepositoryIndexError):
    pass


class IndexCorruptionError(RepositoryIndexError):
    pass


class IndexBuildError(RepositoryIndexError):
    pass


class IndexLockError(RepositoryIndexError):
    pass
