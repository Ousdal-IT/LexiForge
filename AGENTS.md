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
- Before finishing, run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run pytest`, `./scripts/check-repository-hygiene.sh`, and `git diff --check`.
