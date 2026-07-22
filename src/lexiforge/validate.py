import re
import unicodedata
from collections import Counter

from .models import CandidateRecord, Diagnostic, LanguageProfile, Severity, ValidationResult
from .normalize import normalize_word


def validate_candidates(
    records: list[CandidateRecord],
    profile: LanguageProfile,
    categories: set[str],
    blocklist: set[str] | None = None,
) -> ValidationResult:
    diagnostics: list[Diagnostic] = []
    ids = Counter(record.candidate.id for record in records)
    normalized = Counter(normalize_word(record.candidate.word, profile) for record in records)
    allowed = re.compile(profile.allowed_pattern)
    blocked = blocklist or set()

    def add(record: CandidateRecord, rule: str, message: str) -> None:
        candidate = record.candidate
        diagnostics.append(
            Diagnostic(
                rule_id=rule,
                severity=Severity.ERROR,
                message=message,
                language=candidate.language,
                word=candidate.word,
                file=record.file,
                row=record.row,
            )
        )

    for record in records:
        candidate = record.candidate
        word = candidate.word
        canonical = normalize_word(word, profile)
        if candidate.language != profile.code:
            add(record, "language.mismatch", f"expected language {profile.code!r}")
        if candidate.category is not None and candidate.category not in categories:
            add(record, "category.unknown", f"unknown category {candidate.category!r}")
        if ids[candidate.id] > 1:
            add(record, "candidate.duplicate_id", f"duplicate candidate id {candidate.id}")
        if normalized[canonical] > 1:
            add(record, "word.duplicate", f"duplicate normalized word {canonical!r}")
        if word != word.lstrip():
            add(record, "word.leading_whitespace", "leading whitespace is not allowed")
        if word != word.rstrip():
            add(record, "word.trailing_whitespace", "trailing whitespace is not allowed")
        if not profile.allow_internal_whitespace and any(char.isspace() for char in word.strip()):
            add(record, "word.internal_whitespace", "internal whitespace is not allowed")
        if word != unicodedata.normalize(profile.normalization, word):
            add(record, "word.normalization", f"word must use {profile.normalization}")
        if word != word.lower():
            add(record, "word.lowercase", "word must be lowercase")
        if not profile.allow_apostrophes and ("'" in word or "’" in word):
            add(record, "word.apostrophe", "apostrophes are not allowed")
        if not profile.allow_hyphens and "-" in word:
            add(record, "word.hyphen", "hyphens are not allowed")
        if not profile.allow_digits and any(char.isdigit() for char in word):
            add(record, "word.digit", "digits are not allowed")
        if not allowed.fullmatch(canonical):
            add(record, "word.characters", "word does not match the language allowed pattern")
        length = len(canonical)
        if length < profile.word_length.minimum:
            add(
                record, "word.minimum_length", f"word is shorter than {profile.word_length.minimum}"
            )
        if length > profile.word_length.maximum:
            add(record, "word.maximum_length", f"word is longer than {profile.word_length.maximum}")
        if canonical in blocked:
            add(record, "word.blocklisted", "word occurs in a configured blocklist")
    return ValidationResult(diagnostics=diagnostics)
