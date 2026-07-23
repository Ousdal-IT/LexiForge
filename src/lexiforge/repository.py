import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, ValidationError

from .constants import DEFAULT_DATA_ROOT
from .errors import ConfigurationError
from .models import LanguageCode, StrictModel

DATASET_SCHEMA_VERSION = 1
TOOL_VERSION = "0.7.0"


class Compatibility(StrictModel):
    minimum_lexiforge: str
    maximum_lexiforge_exclusive: str


class DatasetManifest(StrictModel):
    dataset_version: str
    schema_version: int = Field(ge=1)
    supported_languages: list[LanguageCode]
    license: str
    maintainer: str
    generated_date: str | None = None
    compatibility: Compatibility


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError as error:
        raise ConfigurationError(f"invalid compatibility version: {value!r}") from error


class DatasetRepository:
    """Resolved, validated boundary around bundled or external dataset files."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    @classmethod
    def resolve(cls, explicit: Path | None = None) -> "DatasetRepository":
        if explicit is not None:
            return cls(explicit)
        environment = os.environ.get("LEXIFORGE_DATA_ROOT")
        return cls(Path(environment) if environment else DEFAULT_DATA_ROOT)

    @property
    def source(self) -> str:
        if self.root == DEFAULT_DATA_ROOT.resolve():
            return "bundled"
        return "external"

    @property
    def writable(self) -> bool:
        return os.access(self.root, os.W_OK)

    def load_manifest(self) -> DatasetManifest:
        path = self.root / "manifest.yaml"
        try:
            raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
            manifest = DatasetManifest.model_validate(raw)
        except FileNotFoundError as error:
            raise ConfigurationError(f"dataset manifest is missing: {path}") from error
        except (OSError, UnicodeError, yaml.YAMLError, ValidationError) as error:
            raise ConfigurationError(f"invalid dataset manifest {path}: {error}") from error
        if manifest.schema_version != DATASET_SCHEMA_VERSION:
            raise ConfigurationError(
                f"dataset schema {manifest.schema_version} is incompatible; "
                f"LexiForge requires schema {DATASET_SCHEMA_VERSION}"
            )
        current = _version_tuple(TOOL_VERSION)
        minimum = _version_tuple(manifest.compatibility.minimum_lexiforge)
        maximum = _version_tuple(manifest.compatibility.maximum_lexiforge_exclusive)
        if not minimum <= current < maximum:
            raise ConfigurationError(
                f"dataset {manifest.dataset_version} requires LexiForge "
                f">={manifest.compatibility.minimum_lexiforge}, "
                f"<{manifest.compatibility.maximum_lexiforge_exclusive}; running {TOOL_VERSION}"
            )
        if len(manifest.supported_languages) != len(set(manifest.supported_languages)):
            raise ConfigurationError("dataset manifest contains duplicate supported languages")
        return manifest

    def validate_layout(self) -> list[str]:
        manifest = self.load_manifest()
        errors: list[str] = []
        required_shared = ["categories.yaml", "policy.yaml", "scoring.yaml", "blocklist-types.yaml"]
        for name in required_shared:
            if not (self.root / "shared" / name).is_file():
                errors.append(f"missing required file: shared/{name}")
        declared = set(manifest.supported_languages)
        languages_root = self.root / "languages"
        detected = (
            {path.name for path in languages_root.iterdir() if path.is_dir()}
            if languages_root.is_dir()
            else set()
        )
        if declared != detected:
            errors.append(
                "manifest/directory language mismatch: "
                f"declared={','.join(sorted(declared))}; detected={','.join(sorted(detected))}"
            )
        required_language = [
            "language.yaml",
            "candidates.csv",
            "provenance.csv",
            "reviews.csv",
            "blocklists/metadata.yaml",
        ]
        for language in sorted(declared):
            for relative in required_language:
                if not (languages_root / language / relative).is_file():
                    errors.append(f"missing required file: languages/{language}/{relative}")
        if not errors:
            from .blocklists import load_blocklists_with_metadata
            from .curation import load_curation_data
            from .errors import LexiForgeError
            from .moderation import validate_review_history
            from .profiles import load_categories, load_policy, load_profiles
            from .provenance import validate_provenance_links
            from .scoring import load_scoring_config

            try:
                profiles = load_profiles(self.root)
                load_categories(self.root)
                load_policy(self.root)
                load_scoring_config(self.root)
                for language in sorted(declared):
                    profile, candidates, provenance, reviews = load_curation_data(
                        language, self.root
                    )
                    load_blocklists_with_metadata(languages_root / language / "blocklists", profile)
                    statuses = {item.candidate.id: item.candidate.status for item in candidates}
                    errors.extend(validate_provenance_links(provenance, set(statuses)))
                    errors.extend(validate_review_history(reviews, statuses))
                if set(profiles) != declared:
                    errors.append("loaded profiles do not match manifest languages")
            except LexiForgeError as error:
                errors.append(str(error))
        return sorted(errors)
