import unicodedata

from lexiforge.normalize import normalize_word
from lexiforge.profiles import load_language_profile


def test_nfc_and_lowercase(nb_profile) -> None:
    decomposed = unicodedata.normalize("NFD", "BLÅ")
    assert normalize_word(decomposed, nb_profile) == "blå"


def test_no_transliteration(nb_profile) -> None:
    assert normalize_word("ÆØÅ", nb_profile) == "æøå"


def test_punctuation_and_whitespace_preserved(nb_profile) -> None:
    assert normalize_word(" Hus-båt ", nb_profile) == " hus-båt "


def test_english_profile_differs() -> None:
    import re

    profile = load_language_profile("en")
    assert re.fullmatch(profile.allowed_pattern, "apple")
    assert not re.fullmatch(profile.allowed_pattern, "blå")
