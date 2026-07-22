import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lexiforge.cli import app
from lexiforge.constants import DEFAULT_DATA_ROOT
from lexiforge.errors import ConfigurationError
from lexiforge.repository import DATASET_SCHEMA_VERSION, DatasetRepository

runner = CliRunner()


def copy_data(tmp_path: Path, name: str = "external") -> Path:
    destination = tmp_path / name
    shutil.copytree(DEFAULT_DATA_ROOT, destination)
    return destination


def directory_bytes(path: Path) -> dict[str, bytes]:
    return {
        str(item.relative_to(path)): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_bundled_repository_manifest_and_layout() -> None:
    repository = DatasetRepository.resolve()
    manifest = repository.load_manifest()
    assert manifest.schema_version == DATASET_SCHEMA_VERSION
    assert set(manifest.supported_languages) == {"nb", "nn", "en"}
    assert repository.validate_layout() == []
    assert repository.source == "bundled"


def test_external_repository(tmp_path: Path) -> None:
    root = copy_data(tmp_path)
    repository = DatasetRepository.resolve(root)
    assert repository.source == "external"
    assert repository.validate_layout() == []


def test_environment_variable_resolution(tmp_path: Path, monkeypatch) -> None:
    root = copy_data(tmp_path)
    monkeypatch.setenv("LEXIFORGE_DATA_ROOT", str(root))
    assert DatasetRepository.resolve().root == root.resolve()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert str(root.resolve()) in result.stdout


def test_cli_override_precedes_environment(tmp_path: Path, monkeypatch) -> None:
    valid = copy_data(tmp_path, "valid")
    monkeypatch.setenv("LEXIFORGE_DATA_ROOT", str(tmp_path / "missing"))
    result = runner.invoke(app, ["validate", "--data-root", str(valid), "--all"])
    assert result.exit_code == 0


def test_missing_manifest_is_rejected_without_fallback(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    with pytest.raises(ConfigurationError, match="manifest is missing"):
        DatasetRepository.resolve(root).load_manifest()


def test_incompatible_manifest(tmp_path: Path) -> None:
    root = copy_data(tmp_path)
    manifest = root / "manifest.yaml"
    content = manifest.read_text(encoding="utf-8").replace(
        "schema_version: 1", "schema_version: 99"
    )
    manifest.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigurationError, match="schema 99 is incompatible"):
        DatasetRepository.resolve(root).load_manifest()


def test_invalid_repository_layout_is_deterministic(tmp_path: Path) -> None:
    root = copy_data(tmp_path)
    (root / "languages/nb/reviews.csv").unlink()
    repository = DatasetRepository.resolve(root)
    first = repository.validate_layout()
    assert first == repository.validate_layout()
    assert first == ["missing required file: languages/nb/reviews.csv"]


def test_doctor_and_repository_validation_commands() -> None:
    doctor = runner.invoke(app, ["doctor"])
    assert doctor.exit_code == 0
    assert "Dataset version: 0.2.5-dev" in doctor.stdout
    assert "profile version 1" in doctor.stdout
    validation = runner.invoke(app, ["validate-repository"])
    assert validation.exit_code == 0
    assert "repository valid" in validation.stdout


def test_external_and_bundled_builds_are_identical(tmp_path: Path) -> None:
    external = copy_data(tmp_path)
    outputs = []
    for name, arguments in (
        ("bundled", []),
        ("external-first", ["--data-root", str(external)]),
        ("external-second", ["--data-root", str(external)]),
    ):
        output = tmp_path / name
        result = runner.invoke(
            app,
            [
                "build",
                *arguments,
                "--language",
                "nb",
                "--size",
                "16",
                "--allow-development-size",
                "--balanced",
                "--output-dir",
                str(output),
            ],
        )
        assert result.exit_code == 0
        outputs.append(directory_bytes(output))
    assert outputs[0] == outputs[1] == outputs[2]


def test_external_report_is_reproducible(tmp_path: Path) -> None:
    external = copy_data(tmp_path)
    outputs = []
    for name in ("first", "second"):
        output = tmp_path / name
        result = runner.invoke(
            app,
            [
                "report",
                "publish",
                "--data-root",
                str(external),
                "--output-dir",
                str(output),
            ],
        )
        assert result.exit_code == 0
        outputs.append(directory_bytes(output))
    assert outputs[0] == outputs[1]


def test_build_default_output_directory_with_external_root(tmp_path: Path, monkeypatch) -> None:
    external = copy_data(tmp_path)
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.chdir(working)
    result = runner.invoke(
        app,
        [
            "build",
            "--data-root",
            str(external),
            "--language",
            "nb",
            "--size",
            "16",
            "--allow-development-size",
        ],
    )
    assert result.exit_code == 0
    assert Path("build/nb/manifest.json").is_file()
