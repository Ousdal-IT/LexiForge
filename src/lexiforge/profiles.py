from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .constants import DEFAULT_DATA_ROOT
from .errors import ConfigurationError, ProfileError
from .models import CategoryConfig, LanguageProfile, SharedPolicy


def _load_yaml(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ConfigurationError(f"cannot load {path}: {error}") from error


def load_language_profile(
    code_or_path: str | Path, data_root: Path = DEFAULT_DATA_ROOT
) -> LanguageProfile:
    path = Path(code_or_path)
    if not path.suffix:
        path = data_root / "languages" / str(code_or_path) / "language.yaml"
    try:
        profile = LanguageProfile.model_validate(_load_yaml(path))
    except ValidationError as error:
        raise ProfileError(f"invalid language profile {path}: {error}") from error
    if path.parent.name != profile.code:
        raise ProfileError(
            f"profile code {profile.code!r} does not match directory {path.parent.name!r}"
        )
    return profile


def load_profiles(data_root: Path = DEFAULT_DATA_ROOT) -> dict[str, LanguageProfile]:
    base = data_root / "languages"
    profiles: dict[str, LanguageProfile] = {}
    for path in sorted(base.glob("*/language.yaml")):
        profile = load_language_profile(path, data_root)
        if profile.code in profiles:
            raise ProfileError(f"duplicate language code: {profile.code}")
        profiles[profile.code] = profile
    if not profiles:
        raise ProfileError(f"no language profiles found in {base}")
    return profiles


def load_policy(data_root: Path = DEFAULT_DATA_ROOT) -> SharedPolicy:
    path = data_root / "shared" / "policy.yaml"
    try:
        return SharedPolicy.model_validate(_load_yaml(path))
    except ValidationError as error:
        raise ConfigurationError(f"invalid policy {path}: {error}") from error


def load_categories(data_root: Path = DEFAULT_DATA_ROOT) -> CategoryConfig:
    path = data_root / "shared" / "categories.yaml"
    try:
        result = CategoryConfig.model_validate(_load_yaml(path))
    except ValidationError as error:
        raise ConfigurationError(f"invalid categories {path}: {error}") from error
    ids = [category.id for category in result.categories]
    if len(ids) != len(set(ids)):
        raise ConfigurationError(f"duplicate category id in {path}")
    languages = set(load_profiles(data_root))
    for category in result.categories:
        missing = languages - set(category.labels)
        if missing:
            raise ConfigurationError(
                f"category {category.id!r} lacks labels for: {', '.join(sorted(missing))}"
            )
    return result
