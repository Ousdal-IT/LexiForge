import unicodedata

from .models import LanguageProfile


def normalize_word(word: str, profile: LanguageProfile) -> str:
    """Return the canonical form without repairing whitespace or punctuation."""
    normalized = unicodedata.normalize(profile.normalization, word)
    return normalized.lower() if profile.output_case == "lowercase" else normalized
