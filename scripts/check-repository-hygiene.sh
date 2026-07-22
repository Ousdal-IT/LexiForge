#!/usr/bin/env bash
set -euo pipefail

required=(README.md AGENTS.md CHANGELOG.md CONTRIBUTING.md CODE_OF_CONDUCT.md SECURITY.md LICENSE LICENSE-DATA THIRD_PARTY.md pyproject.toml uv.lock)
for path in "${required[@]}"; do
  test -f "$path" || { echo "missing required file: $path" >&2; exit 1; }
done

tracked_files=""
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  tracked_files="$(git ls-files)"
fi

if grep -E '(^|/)(__pycache__|\.venv)(/|$)|\.pyc$' <<<"$tracked_files" >/dev/null; then
  echo "Python cache or virtual environment is committed" >&2
  exit 1
fi

if find releases -type f ! -name .gitkeep -print | grep -q .; then
  echo "generated release artefacts must not be committed" >&2
  exit 1
fi

python - <<'PY'
from pathlib import Path

text_suffixes = {".md", ".py", ".toml", ".yaml", ".yml", ".csv", ".txt", ".sh", ".json"}
ignored = {".git", ".venv", ".pytest_cache", ".mypy_cache", ".ruff_cache", "build", "dist"}
for path in sorted(Path(".").rglob("*")):
    if not path.is_file() or ignored.intersection(path.parts) or path.suffix not in text_suffixes:
        continue
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise SystemExit(f"not UTF-8: {path}: {error}")
    if content and not content.endswith("\n"):
        raise SystemExit(f"missing final newline: {path}")
    for number, line in enumerate(content.splitlines(), 1):
        if line.rstrip() != line:
            raise SystemExit(f"trailing whitespace: {path}:{number}")

for profile in sorted(Path("data/languages").glob("*/language.yaml")):
    code_line = next((line for line in profile.read_text(encoding="utf-8").splitlines() if line.startswith("code:")), "")
    if code_line.partition(":")[2].strip() != profile.parent.name:
        raise SystemExit(f"language directory/profile mismatch: {profile}")
PY

if grep -Ei '(^|/)(dictionary|dictionaries|wordlist|passwords?)[-_].*\.(txt|csv|json)$' <<<"$tracked_files" >/dev/null; then
  echo "possible raw third-party dictionary dump is committed" >&2
  exit 1
fi

echo "repository hygiene: ok"
