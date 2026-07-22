from pathlib import Path

from typer.testing import CliRunner

from lexiforge.cli import app

runner = CliRunner()


def test_help_and_languages() -> None:
    assert runner.invoke(app, ["--help"]).exit_code == 0
    result = runner.invoke(app, ["languages"])
    assert result.exit_code == 0 and all(code in result.stdout for code in ("nb", "nn", "en"))


def test_validate_and_analyse() -> None:
    assert runner.invoke(app, ["validate", "--all"]).exit_code == 0
    result = runner.invoke(app, ["analyse", "--language", "nb", "--format", "json"])
    assert result.exit_code == 0 and '"language": "nb"' in result.stdout


def test_export(tmp_path: Path) -> None:
    output = tmp_path / "nb.txt"
    result = runner.invoke(
        app, ["export", "--language", "nb", "--format", "txt", "--output", str(output)]
    )
    assert result.exit_code == 0 and output.read_bytes().endswith(b"\n")


def test_reproducible_builds(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LC_ALL", "C")
    outputs = []
    for name in ("one", "two"):
        directory = tmp_path / name
        result = runner.invoke(app, ["build", "--language", "nn", "--output-dir", str(directory)])
        assert result.exit_code == 0
        outputs.append({path.name: path.read_bytes() for path in directory.iterdir()})
    assert outputs[0] == outputs[1]


def test_invalid_usage_exit_code() -> None:
    assert runner.invoke(app, ["validate"]).exit_code == 2
