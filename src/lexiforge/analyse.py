from collections import Counter
from typing import Any

from .models import CandidateRecord, LanguageProfile, ValidationResult
from .normalize import normalize_word


def analyse_candidates(
    records: list[CandidateRecord], profile: LanguageProfile, validation: ValidationResult
) -> dict[str, Any]:
    words = [normalize_word(record.candidate.word, profile) for record in records]
    lengths = [len(word) for word in words]
    statuses = Counter(record.candidate.status.value for record in records)
    categories = Counter(record.candidate.category or "uncategorized" for record in records)
    characters = Counter(char for word in words for char in word)
    return {
        "schema_version": 1,
        "language": profile.code,
        "total_records": len(records),
        "unique_normalized_words": len(set(words)),
        "records_by_status": dict(sorted(statuses.items())),
        "records_by_category": dict(sorted(categories.items())),
        "minimum_word_length": min(lengths, default=0),
        "maximum_word_length": max(lengths, default=0),
        "average_word_length": round(sum(lengths) / len(lengths), 3) if lengths else 0.0,
        "character_frequency": dict(sorted(characters.items())),
        "words_with_non_ascii_letters": sum(
            any(ord(char) > 127 for char in word) for word in words
        ),
        "duplicate_candidates": len(words) - len(set(words)),
        "validation_error_count": validation.error_count,
        "validation_warning_count": validation.warning_count,
    }
