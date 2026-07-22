from pathlib import Path

import pytest

from lexiforge.errors import ExportError
from lexiforge.manifest import create_manifest, sha256_file, verify_manifest, write_manifest


def test_manifest_hash_and_determinism(tmp_path: Path, nb_profile) -> None:
    exported = tmp_path / "words.txt"
    exported.write_bytes(b"skog\n")
    first = create_manifest(nb_profile, 1, [exported])
    second = create_manifest(nb_profile, 1, [exported])
    assert first == second
    assert first["files"][0]["sha256"] == sha256_file(exported)
    one = write_manifest(first, tmp_path / "one.json").read_bytes()
    two = write_manifest(second, tmp_path / "two.json").read_bytes()
    assert one == two and one.endswith(b"\n")


def test_manifest_mismatch(tmp_path: Path, nb_profile) -> None:
    exported = tmp_path / "words.txt"
    exported.write_bytes(b"skog\n")
    manifest = create_manifest(nb_profile, 1, [exported])
    with pytest.raises(ExportError, match="word count"):
        verify_manifest(manifest, tmp_path, 2)
