# LexiForge

LexiForge is an open platform for building, curating, validating, analysing, and publishing high-quality multilingual passphrase wordlists. Passphrase lists need careful curation because structural correctness, unambiguous spelling, provenance, and reproducible releases all affect their usefulness.

M0 supports Norwegian Bokmål (`nb`), Norwegian Nynorsk (`nn`), and English (`en`) as equal, configuration-driven language profiles. The included words are small, project-created examples for testing the tooling. **They are not production security wordlists.**

## Install and use

Python 3.12 or newer and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --frozen --all-extras --dev
uv run lexiforge languages
uv run lexiforge validate --all
uv run lexiforge analyse --all --format markdown
uv run lexiforge export --language nb --format txt --output build/nb.txt
uv run lexiforge build --language nb --output-dir build/nb
```

The CLI exits with 0 on success, 1 for validation/build failures, and 2 for invalid CLI usage or configuration detected by argument parsing. Expected errors are printed without tracebacks.

## Design and repository

Profiles and candidate CSVs live under `data/languages/`; shared category and policy configuration lives under `data/shared/`. The typed package in `src/lexiforge/` loads, normalizes, validates, analyses, exports, and manifests that data. Tests, documentation, CI, and repository-hygiene checks are kept in their corresponding top-level directories.

Exports select approved candidates, normalize them, and sort by Unicode code-point order. TXT, JSON, and CSV encodings are stable UTF-8 with final newlines. Builds contain no volatile timestamps and include SHA-256 hashes.

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
./scripts/check-repository-hygiene.sh
git diff --check
```

Core tooling is local-only: it performs no telemetry or network requests. See `docs/`, `CONTRIBUTING.md`, and `AGENTS.md` before changing behavior or data.

## Licensing

Code, tests, tooling, and documentation are MIT licensed. Eligible independently created LexiForge data is intended for CC0 1.0; this applies only when LexiForge has the right to make that dedication. Third-party material retains its source license. See `docs/licensing.md`, `LICENSE-DATA`, and `THIRD_PARTY.md`.

