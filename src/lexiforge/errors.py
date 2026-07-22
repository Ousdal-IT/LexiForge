class LexiForgeError(Exception):
    """Base class for expected LexiForge errors."""


class ConfigurationError(LexiForgeError):
    """Configuration is missing or invalid."""


class ProfileError(ConfigurationError):
    """A language profile is invalid."""


class DataFormatError(LexiForgeError):
    """Candidate input cannot be parsed."""


class ValidationFailure(LexiForgeError):
    """Validation prevents an operation."""


class ExportError(LexiForgeError):
    """An export could not be produced or verified."""
