"""Release-level wheel contract checks; run with LEXIFORGE_RUN_RELEASE_TESTS=1."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.release,
    pytest.mark.skipif(
        os.environ.get("LEXIFORGE_RUN_RELEASE_TESTS") != "1",
        reason="set LEXIFORGE_RUN_RELEASE_TESTS=1 for wheel release checks",
    ),
]


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def _data_files(root: Path) -> set[str]:
    return {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}


def test_regular_wheel_contains_and_uses_bundled_dataset(tmp_path: Path) -> None:
    project = Path(__file__).parents[1].resolve()
    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("LEXIFORGE_DATA_ROOT", None)
    env["HOME"] = str(tmp_path / "home")
    env["XDG_CACHE_HOME"] = str(tmp_path / "cache")

    _run(["uv", "build", "--wheel", "--out-dir", str(wheel_dir)], cwd=project, env=env)
    wheels = sorted(wheel_dir.glob("lexiforge-*.whl"))
    assert len(wheels) == 1
    wheel = wheels[0]

    with zipfile.ZipFile(wheel) as archive:
        packaged_data = {
            name.removeprefix("data/")
            for name in archive.namelist()
            if name.startswith("data/") and not name.endswith("/")
        }
    assert packaged_data == _data_files(project / "data")

    venv = tmp_path / "venv"
    _run([sys.executable, "-m", "venv", str(venv)], cwd=project, env=env)
    python = venv / "bin/python"
    executable = venv / "bin/lexiforge"
    _run(["uv", "pip", "install", "--python", str(python), str(wheel)], cwd=project, env=env)

    assert "Usage:" in _run([str(executable), "--help"], cwd=tmp_path, env=env)
    doctor = _run([str(executable), "doctor"], cwd=tmp_path, env=env)
    assert "Data source: bundled" in doctor
    assert "Access: read-only" in doctor
    assert str(project / "data") not in doctor

    external = tmp_path / "external-data"
    shutil.copytree(project / "data", external)
    external_doctor = _run(
        [str(executable), "doctor", "--data-root", str(external)], cwd=tmp_path, env=env
    )
    assert "Data source: external" in external_doctor
    assert str(external.resolve()) in external_doctor

    missing = subprocess.run(
        [str(executable), "doctor", "--data-root", str(tmp_path / "missing")],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )
    assert missing.returncode == 2
    assert "error: dataset manifest is missing" in missing.stderr

    package_root = Path(
        _run(
            [str(python), "-c", "import lexiforge; print(lexiforge.__file__)"],
            cwd=tmp_path,
            env=env,
        ).strip()
    ).parent
    assert not any(
        path.name in {"index.sqlite3", "desktop.json"} for path in package_root.rglob("*")
    )
