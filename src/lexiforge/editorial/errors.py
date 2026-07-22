class EditorialError(Exception):
    """Base exception for expected editorial-service failures."""


class ValidationError(EditorialError):
    """A proposed repository state does not pass existing validators."""


class DuplicateCandidateError(ValidationError):
    """A proposed change duplicates a language-scoped normalized word."""


class RepositoryStateError(EditorialError):
    """The repository no longer matches the state used for preview."""


class MutationRejectedError(EditorialError):
    """An operation or changeset is unsafe or cannot be applied."""
