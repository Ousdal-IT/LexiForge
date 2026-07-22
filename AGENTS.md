# Working on LexiForge

LexiForge builds deterministic, multilingual passphrase-wordlist artefacts. M0 is local Python tooling only: do not add a website, service, database, authentication, telemetry, or network behavior.

- Keep `nb`, `nn`, and `en` first-class. Put language rules in strict `language.yaml` profiles; never scatter language-code conditionals through core logic.
- Same inputs and configuration must yield byte-identical output. Avoid time, randomness, locale sorting, filesystem-order assumptions, and manual edits to generated releases.
- Core stages are loading, normalization, structural validation, analysis, approved-word selection, deterministic export, and hash manifesting. Keep normalization non-destructive and separate from acceptance.
- MIT covers code and docs. CC0 applies only to eligible LexiForge-created data with verified rights. Never casually add dictionaries, bulk wordlists, definitions, or other third-party datasets; document all provenance and licenses.
- Use Python 3.12+, typed code, standard library where practical, strict Pydantic models, safe YAML, Ruff, mypy, and pytest. No runtime network dependency.
- Update documentation and tests with behavior or schema changes. Invalid examples belong under `tests/fixtures`, not production data.
- Before finishing, run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run pytest`, `./scripts/check-repository-hygiene.sh`, and `git diff --check`.

