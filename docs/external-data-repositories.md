# External data repositories

LexiForge is the offline tooling repository. The planned `LexiForge-Data` repository will hold canonical official datasets, while a future `LexiForge-Web` repository may provide submission and moderation interfaces. Additional language repositories, SDKs, and integrations may be added independently. The web layer must produce data compatible with this same local validation boundary; it does not replace tooling or make release decisions.

These names describe project organization, not runtime coupling. The tool receives the path to a dataset-interface root and never discovers a sibling checkout or examines Git metadata. The interface may be implemented by any local directory regardless of repository name, nesting, source-control system, or delivery mechanism.

## Selecting a repository

Resolution order is:

1. Per-command `--data-root PATH`
2. `LEXIFORGE_DATA_ROOT`
3. Bundled development `data/`

The bundled development dataset is included in source checkouts, editable installs, and regular
LexiForge wheels. A regular wheel places it beside the installed package as `data/`; it is a
read-only example dataset and is not an official production release. Normal mutation commands
should target an explicitly supplied writable external repository such as `LexiForge-Data`.

An explicit or environment root that is absent, malformed, or incompatible fails clearly. LexiForge never falls back to bundled data after a higher-priority root was selected.

```bash
uv run lexiforge doctor --data-root ../lexiforge-data/data
uv run lexiforge validate-repository --data-root ../lexiforge-data/data
uv run lexiforge validate --data-root ../lexiforge-data/data --all
```

## Recommended layout

The data root contains `manifest.yaml`, `shared/`, and `languages/`. Every manifest-declared language requires `language.yaml`, `candidates.csv`, `provenance.csv`, `reviews.csv`, and `blocklists/metadata.yaml`. Shared category, policy, scoring, and blocklist-type configuration is mandatory. Reports and builds remain generated output and should not be committed as source data.

## Manifest and compatibility

`manifest.yaml` declares dataset and schema versions, languages, license, maintainer, optional generated date, and an inclusive minimum/exclusive maximum LexiForge version. M2.5 supports dataset schema 1. Profile files independently carry version 1. Compatibility is checked before ordinary data loading.

Generated dates are optional provenance metadata. They must not be injected into deterministic build artefacts unless explicitly sourced from the dataset and included by a documented schema change.

## Migration strategy

To create `LexiForge-Data`, copy the complete bundled `data/` directory, retain its manifest and licensing documentation, run repository validation, and compare an external build byte-for-byte with the bundled build. Then change dataset version and maintainer only as part of a reviewed data release. Do not invent provenance, rewrite review history, or copy third-party word sources during migration.

Bundled datasets remain development examples after separation. Official status belongs to the external repository's reviewed manifest and release process, not its filesystem location alone.

The normative file contract is documented in `dataset-interface.md`.
