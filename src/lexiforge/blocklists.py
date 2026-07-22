from pathlib import Path

import yaml
from pydantic import Field, ValidationError

from .errors import ConfigurationError, DataFormatError
from .models import LanguageCode, LanguageProfile, StrictModel
from .normalize import normalize_word


class BlocklistMetadata(StrictModel):
    id: str
    file: str
    language: LanguageCode
    type: str
    severity: str
    description: str
    license: str
    version: int = Field(ge=1)


class BlocklistConfig(StrictModel):
    blocklists: list[BlocklistMetadata]


class BlocklistMatch(StrictModel):
    blocklist_id: str
    word: str
    severity: str
    type: str


def load_blocklists_with_metadata(
    directory: Path, profile: LanguageProfile
) -> tuple[list[BlocklistMetadata], list[BlocklistMatch], set[str]]:
    metadata_path = directory / "metadata.yaml"
    if not metadata_path.exists():
        return [], [], set()
    try:
        config = BlocklistConfig.model_validate(
            yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        )
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError) as error:
        raise ConfigurationError(f"invalid blocklist metadata {metadata_path}: {error}") from error
    words: set[str] = set()
    matches: list[BlocklistMatch] = []
    for item in config.blocklists:
        if item.language != profile.code:
            raise ConfigurationError(f"blocklist {item.id} language does not match {profile.code}")
        if item.type not in {
            "reserved",
            "offensive",
            "proper_name",
            "brand",
            "sensitive",
            "ambiguous",
            "technical",
            "custom",
        }:
            raise ConfigurationError(f"blocklist {item.id} has unsupported type {item.type}")
        if item.severity not in {"error", "warning", "review"}:
            raise ConfigurationError(
                f"blocklist {item.id} has unsupported severity {item.severity}"
            )
        path = directory / item.file
        content = path.read_text(encoding="utf-8")
        if content and not content.endswith("\n"):
            raise DataFormatError(f"blocklist {path} must end with a newline")
        local: set[str] = set()
        for line_number, line in enumerate(content.splitlines(), 1):
            word = line.strip()
            if not word or word.startswith("#"):
                continue
            if normalize_word(word, profile) != word:
                raise DataFormatError(f"{path}:{line_number}: blocklist entry is not normalized")
            if word in local:
                raise DataFormatError(f"{path}:{line_number}: duplicate blocklist entry {word!r}")
            local.add(word)
            matches.append(
                BlocklistMatch(
                    blocklist_id=item.id, word=word, severity=item.severity, type=item.type
                )
            )
        words.update(local)
    return config.blocklists, matches, words
