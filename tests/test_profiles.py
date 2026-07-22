from pathlib import Path

import pytest

from lexiforge.errors import ProfileError
from lexiforge.profiles import load_categories, load_language_profile, load_profiles


def test_load_all_profiles() -> None:
    assert set(load_profiles()) == {"en", "nb", "nn"}


@pytest.mark.parametrize("code, sample", [("nb", "blå"), ("nn", "øyre"), ("en", "river")])
def test_patterns_accept_examples(code: str, sample: str) -> None:
    import re

    assert re.fullmatch(load_language_profile(code).allowed_pattern, sample)


def test_malformed_profile(tmp_path: Path) -> None:
    directory = tmp_path / "languages" / "xx"
    directory.mkdir(parents=True)
    (directory / "language.yaml").write_text("code: xx\nunknown: true\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="invalid language profile"):
        load_language_profile(directory / "language.yaml", tmp_path)


def test_category_labels_are_complete() -> None:
    assert all(set(item.labels) == {"nb", "nn", "en"} for item in load_categories().categories)


def test_duplicate_profile_code(tmp_path: Path, data_root: Path) -> None:
    import shutil

    shutil.copytree(data_root, tmp_path / "data")
    duplicate = tmp_path / "data/languages/nb-copy"
    shutil.copytree(tmp_path / "data/languages/nb", duplicate)
    with pytest.raises(ProfileError, match="does not match directory"):
        load_profiles(tmp_path / "data")
