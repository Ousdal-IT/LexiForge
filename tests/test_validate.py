import pytest
from conftest import record

from lexiforge.validate import validate_candidates


def rules(records, nb_profile, categories, blocklist=None):
    return {
        item.rule_id
        for item in validate_candidates(records, nb_profile, categories, blocklist).diagnostics
    }


def test_valid_records(nb_records, nb_profile, categories) -> None:
    assert validate_candidates(nb_records, nb_profile, categories).valid


@pytest.mark.parametrize(
    "word,rule",
    [
        (" Skog", "word.leading_whitespace"),
        ("skog ", "word.trailing_whitespace"),
        ("stor skog", "word.internal_whitespace"),
        ("Skog", "word.lowercase"),
        ("skog!", "word.characters"),
        ("a", "word.minimum_length"),
        ("abcdefghijklmnop", "word.maximum_length"),
        ("båt-bru", "word.hyphen"),
        ("båt2", "word.digit"),
    ],
)
def test_word_rules(word, rule, nb_profile, categories) -> None:
    assert rule in rules([record(word=word)], nb_profile, categories)


def test_duplicate_word_and_id(nb_profile, categories) -> None:
    records = [record(), record()]
    found = rules(records, nb_profile, categories)
    assert {"word.duplicate", "candidate.duplicate_id"} <= found


def test_same_spelling_across_languages_is_separate(categories) -> None:
    from lexiforge.profiles import load_language_profile

    assert validate_candidates([record(word="eple")], load_language_profile("nb"), categories).valid
    nn = record(id="90000000-0000-4000-8000-000000000002", language="nn", word="eple")
    assert validate_candidates([nn], load_language_profile("nn"), categories).valid


def test_metadata_and_blocklist_rules(nb_profile, categories) -> None:
    found = rules([record(language="en", category="unknown")], nb_profile, categories, {"skog"})
    assert {"language.mismatch", "category.unknown", "word.blocklisted"} <= found
