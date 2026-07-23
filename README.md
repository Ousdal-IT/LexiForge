# LexiForge

LexiForge is an open platform for building, curating, validating, analysing, and publishing high-quality multilingual passphrase wordlists. Passphrase lists need careful curation because structural correctness, unambiguous spelling, provenance, and reproducible releases all affect their usefulness.

M1 supports Norwegian Bokmål (`nb`), Norwegian Nynorsk (`nn`), and English (`en`) as equal, configuration-driven language profiles. It adds provenance, append-only human reviews, blocklist metadata, advisory similarity/scoring, release eligibility, and dry-run local workflows. The included words are small, project-created examples for testing the tooling. **They are not production security wordlists.**

## Install and use

Python 3.12 or newer and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --frozen --all-extras --dev
uv run lexiforge languages
uv run lexiforge validate --all
uv run lexiforge analyse --all --format markdown
uv run lexiforge export --language nb --format txt --output build/nb.txt
uv run lexiforge build --language nb --output-dir build/nb
uv run lexiforge similarity --language nb
uv run lexiforge score --language nb
uv run lexiforge curate report --all --format markdown
uv run lexiforge build --language nb --size 16 --allow-development-size --output-dir build/nb-dev
uv run lexiforge optimise --all
uv run lexiforge compare nb nn
uv run lexiforge release plan
uv run lexiforge report generate --language nb --format html --output build/nb-report.html
uv run lexiforge report publish --output-dir build/site
uv run lexiforge build --language nb --size 16 --allow-development-size --balanced --output-dir build/nb-balanced
uv run lexiforge doctor
uv run lexiforge validate-repository
uv run lexiforge validate --data-root ../lexiforge-data/data --all
uv run lexiforge editor --data-root ../lexiforge-data/data
```

The CLI exits with 0 on success, 1 for validation/build failures, and 2 for invalid CLI usage or configuration detected by argument parsing. Expected errors are printed without tracebacks.

## Design and repository

Profiles and candidate CSVs live under `data/languages/`; shared category and policy configuration lives under `data/shared/`. The typed package in `src/lexiforge/` loads, normalizes, validates, analyses, exports, and manifests that data. Tests, documentation, CI, and repository-hygiene checks are kept in their corresponding top-level directories.

Exports normalize eligible approved candidates and sort by Unicode code-point order. Eligibility requires provenance, licensing, resolved human criteria, and no error blocklist or mandatory flag. Scores never approve words. TXT, JSON, CSV, reports, and manifests contain no volatile build timestamps.

M2 dataset engineering adds n-gram and distribution statistics, advisory optimisation, target-gap planning, structural language comparison, deterministic balanced selection, and static Markdown/JSON/HTML/SVG reporting. It never invents words or changes moderation decisions.

## External dataset repositories

Every data-aware command resolves its dataset-interface root in this order: an explicit `--data-root`, `LEXIFORGE_DATA_ROOT`, then bundled development data. A supplied root must contain a compatible `manifest.yaml`; invalid external data is rejected without silently falling back. No Git checkout name, remote, or sibling layout is assumed. Run `lexiforge doctor` to see the resolved root and `lexiforge validate-repository` before builds. See `docs/dataset-interface.md` and `docs/external-data-repositories.md` for the file contract and migration policy.

## Editorial service

`lexiforge.editorial` is the UI-independent mutation boundary for every editor. It creates immutable validated `ChangeSet` previews, detects stale repository state, validates proposed content in an isolated repository copy, and applies text files atomically with rollback. M3.1 adds dry-run-first `candidates`, `provenance`, and `review` workflows without moving business rules into the CLI; see `docs/editorial-cli.md` and `docs/editorial-service.md`.

M3.2 adds the preferred full-screen Textual workbench through `lexiforge editor`. It browses and filters a cached read snapshot, renders the existing deterministic previews, and applies only validated service change sets. See `docs/editorial-workbench.md` for workflows and keyboard shortcuts.

M3.3 adds the editorial dashboard, combinable power filters, saved searches, batch review, statistics, similarity and duplicate tools, comparison, blocklist operations, import-review mode, and external session persistence. See `docs/editorial-power-tools.md` for the power-user guide.

Repository statistics are also available without opening the workbench: `uv run lexiforge stats --format json` (or `--format csv`).

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
