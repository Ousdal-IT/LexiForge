# Changelog

## 0.7.0 - Unreleased

- Establish the multilingual M0 package, CLI, validation, analysis, deterministic exports, manifests, documentation, tests, and CI.
- Add M1 provenance, reviews, transitions, blocklist metadata, similarity, scoring, curation reports, safe local workflows, and development-size builds.
- Add M2 dataset statistics, read-only optimisation, release planning, structural comparison, balanced selection, and static HTML/SVG publication.
- Add M2.5 external dataset roots, manifests, compatibility checks, repository discovery, validation, and bundled/external reproducibility.
- Add the M3.0 UI-independent editorial service, immutable changesets, deterministic previews, structured errors, shadow validation, atomic apply, and rollback.
- Add M3.1 typed candidate, provenance, and review operations with service-backed dry-run/apply CLI workflows, explicit audit metadata, deterministic structured diffs, and schema-safe limitations.
- Add the M3.2 Textual editorial workbench with cached browsing, filtering, search, detail panels, modal operation forms, deterministic previews, and service-only application.
- Add M3.3 power tools: dashboard statistics, advanced filters, saved-search/session persistence, batch review, similarity and duplicate assistants, candidate comparison, blocklist operations, and import-review mode.
- Harden batch approval: require explicit canonical review criteria, validate every candidate before writing, report per-candidate failures, and apply successful batches atomically.
- Add the disposable SQLite repository index, deterministic fingerprints, index lifecycle CLI, canonical fallback, and indexed read primitives for lookup, search, statistics, provenance, reviews, and similarity candidate generation.
- Harden M4.0 with canonical/index search, filtering, ordering, statistics, eligibility and Unicode parity; deterministic metadata; strict SQLite integrity checks; pre/post-build fingerprints; ownership-aware locks; and corruption-safe fallback.
- Integrate the hardened repository index into the Textual workbench through a typed backend-neutral query layer with bounded pagination, lazy details, indexed dashboard reads, canonical fallback, mutation invalidation, and background full rebuilds.
