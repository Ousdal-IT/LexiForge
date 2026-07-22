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
    length_histogram = Counter(str(length) for length in lengths)
    first_letters = Counter(word[0] for word in words if word)
    last_letters = Counter(word[-1] for word in words if word)
    bigrams = Counter(word[index : index + 2] for word in words for index in range(len(word) - 1))
    trigrams = Counter(word[index : index + 3] for word in words for index in range(len(word) - 2))
    vowels = set(profile.vowels)
    vowel_count = sum(char in vowels for word in words for char in word)
    letter_count = sum(char.isalpha() for word in words for char in word)
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
        "word_length_histogram": dict(
            sorted(length_histogram.items(), key=lambda item: int(item[0]))
        ),
        "first_letter_frequency": dict(sorted(first_letters.items())),
        "last_letter_frequency": dict(sorted(last_letters.items())),
        "character_frequency": dict(sorted(characters.items())),
        "bigram_frequency": dict(sorted(bigrams.items())),
        "trigram_frequency": dict(sorted(trigrams.items())),
        "vowel_consonant_statistics": {
            "vowels": vowel_count,
            "consonants": letter_count - vowel_count,
            "vowel_ratio": round(vowel_count / letter_count, 3) if letter_count else 0.0,
        },
        "words_with_non_ascii_letters": sum(
            any(ord(char) > 127 for char in word) for word in words
        ),
        "duplicate_candidates": len(words) - len(set(words)),
        "validation_error_count": validation.error_count,
        "validation_warning_count": validation.warning_count,
    }
