# Working on LexiForge

LexiForge builds deterministic, multilingual passphrase-wordlist artefacts. M0 is local Python tooling only: do not add a website, service, database, authentication, telemetry, or network behavior.

- Keep `nb`, `nn`, and `en` first-class. Put language rules in strict `language.yaml` profiles; never scatter language-code conditionals through core logic.
- Same inputs and configuration must yield byte-identical output. Avoid time, randomness, locale sorting, filesystem-order assumptions, and manual edits to generated releases.
- Core stages are loading, normalization, structural validation, analysis, approved-word selection, deterministic export, and hash manifesting. Keep normalization non-destructive and separate from acceptance.
- MIT covers code and docs. CC0 applies only to eligible LexiForge-created data with verified rights. Never casually add dictionaries, bulk wordlists, definitions, or other third-party datasets; document all provenance and licenses.
- Use Python 3.12+, typed code, standard library where practical, strict Pydantic models, safe YAML, Ruff, mypy, and pytest. No runtime network dependency.
- Update documentation and tests with behavior or schema changes. Invalid examples belong under `tests/fixtures`, not production data.
- Provenance is mandatory for release eligibility and review history is append-only. Scores and similarity findings are advisory; never automate semantic approval.
- Local mutation commands default to dry-run, stage complete UTF-8 files, and replace atomically only with `--apply`. Never manually edit generated reports or releases.
- Third-party and bulk data require explicit provenance and license review. Do not infer CC0 eligibility or conceal a source.
- Dataset optimisation and comparison remain read-only and non-semantic. Balanced selection must remain documented, deterministic, and downstream of release eligibility.
- Static HTML/SVG reports contain no JavaScript, network assets, volatile timestamps, or manually edited generated output.
- Resolve dataset roots through `DatasetRepository`: explicit CLI option, environment, then bundled development data. Never silently fall back from an invalid selected repository.
- Dataset schema/profile compatibility and complete repository layout must pass before normal commands. Keep tooling, canonical data, and future web concerns in separate repositories.
- Treat the data root as an interface, not a Git topology: never assume repository names, sibling locations, remotes, branches, or hosting. Future languages, SDKs, and integrations must couple only through the versioned dataset contract.
- All future repository mutations must go through `EditorialService`; UI, CLI, terminal, and desktop code must never manipulate CSV directly. Existing validators remain the single source of truth—compose them, never duplicate their rules.
- Editorial previews and changeset IDs must be deterministic. Apply only previously validated, non-stale changesets through atomic writes with rollback, and avoid unrelated file diffs.
- Candidate, provenance, and review commands are thin operation adapters. Audit timestamps and actor IDs are explicit and never inferred; edits never change candidate IDs; review history is append-only and provenance history is preserved.
- Mutations default to dry-run and require `--apply`. Approval is always human and explicit. Normalize duplicate checks through language profiles, validate the complete repository after apply, and test against temporary copies—never mutate bundled fixtures.
- Keep terminal/desktop prompting and rendering out of the service layer. Do not introduce TUI or GUI logic into operation planners.
- The Textual workbench is presentation-only: forms construct existing operation objects, previews use the shared renderer, and apply calls `EditorialService`. Never add CSV writes or duplicate domain rules under `workbench/`.
- Keep repository browsing responsive by reusing the immutable workbench snapshot until explicit reload. Do not run all-pairs similarity or reparse full datasets on each keystroke.
- Textual tests run headless against temporary repository copies. Widget tests may inspect presentation behavior but must leave moderation and eligibility rule coverage in the editorial-service tests.
- Power tools may cache read models, statistics, searches, similarity findings, and session state, but session/configuration files must remain outside the dataset. Batch and blocklist writes must produce one validated `ChangeSet` through `EditorialService`; partial or direct CSV writes are prohibited.
- Before finishing, run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run pytest`, `./scripts/check-repository-hygiene.sh`, and `git diff --check`.
- Repository indexes are disposable derived state: canonical files remain authoritative, stale indexes must never be queried, and validation must work without an index. Build indexes in temporary storage with atomic replacement; preserve canonical mutations if refresh fails. Use typed deterministic index queries for read-heavy workflows, keep approval-critical duplicate checks complete, and never mutate data through the index.
