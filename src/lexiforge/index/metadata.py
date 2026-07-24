"""Canonical fingerprints used to validate derived indexes."""

import hashlib
import json

from ..repository import DATASET_SCHEMA_VERSION, TOOL_VERSION, DatasetRepository
from .storage import content_hash

FORMAT_VERSION = 1


def logical_files(repository: DatasetRepository) -> tuple[str, ...]:
    return tuple(
        sorted(
            path.relative_to(repository.root).as_posix()
            for path in repository.root.rglob("*")
            if path.is_file() and ".lexiforge-index" not in path.parts
        )
    )


def file_fingerprints(repository: DatasetRepository) -> dict[str, str]:
    return {
        relative: content_hash(repository.root / relative) for relative in logical_files(repository)
    }


def profile_fingerprints(repository: DatasetRepository) -> dict[str, str]:
    result: dict[str, str] = {}
    for language in _languages(repository):
        path = repository.root / "languages" / language / "language.yaml"
        result[language] = content_hash(path)
    return result


def _languages(repository: DatasetRepository) -> tuple[str, ...]:
    manifest = repository.load_manifest()
    return tuple(sorted(manifest.supported_languages))


def repository_identity(files: dict[str, str]) -> str:
    payload = json.dumps(dict(sorted(files.items())), ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def compatibility_fingerprint(repository: DatasetRepository) -> str:
    payload = f"{TOOL_VERSION}:{DATASET_SCHEMA_VERSION}:{FORMAT_VERSION}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()
