import hashlib
import json
from pathlib import Path
from typing import Any

from .constants import DATA_LICENSE, MANIFEST_SCHEMA_VERSION, PROJECT_NAME, WORDLIST_VERSION
from .errors import ExportError
from .models import LanguageProfile


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_manifest(profile: LanguageProfile, word_count: int, files: list[Path]) -> dict[str, Any]:
    entries = [
        {"format": path.suffix.removeprefix("."), "path": path.name, "sha256": sha256_file(path)}
        for path in sorted(files, key=lambda item: item.name)
    ]
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "wordlist_version": WORDLIST_VERSION,
        "language": profile.code,
        "language_profile": profile.model_dump(mode="json"),
        "word_count": word_count,
        "normalization": profile.normalization,
        "license": DATA_LICENSE,
        "files": entries,
    }


def write_manifest(manifest: dict[str, Any], path: Path) -> Path:
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def verify_manifest(manifest: dict[str, Any], directory: Path, expected_count: int) -> None:
    if manifest["word_count"] != expected_count:
        raise ExportError("manifest word count does not match exported word count")
    for entry in manifest["files"]:
        path = directory / entry["path"]
        if sha256_file(path) != entry["sha256"]:
            raise ExportError(f"manifest hash mismatch for {path.name}")
