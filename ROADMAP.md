# LexiForge roadmap

- **M0 — Foundation:** multilingual profiles, structural validation, deterministic export and manifests.
- **M1 — Local curation:** provenance, reviews, transitions, blocklists, similarity, scoring, and release eligibility.
- **M2 — Dataset engineering:** statistics, optimisation advice, release planning, structural comparison, balanced deterministic builds, and static publication reports.
- **M2.5 — External data support:** manifest compatibility, repository discovery/validation, and deterministic bundled/external parity.
- **M3.0 — Editorial service:** shared operation, preview, validation, changeset, atomic application, and rollback architecture for future editors.
- **M3.1 — Editorial CLI:** dry-run-first candidate, provenance, and append-only review workflows backed exclusively by the editorial service.
- **M3.2 — Editorial workbench:** the local Textual browser/editor, implemented as a thin consumer of M3.1 operations with no new mutation path.
- **M3.3 — Editorial power tools:** dashboard, combinable filters, saved searches, batch review, similarity/duplicate assistance, comparison, blocklist operations, statistics, and session persistence.
- **M3.4 — Workbench refinement:** prospective accessibility, large-repository profiling, richer exact replacement selection, and user-tested editorial ergonomics without changing the dataset schema.
- **M4.0 — Local repository indexing:** disposable SQLite derived state, deterministic fingerprints, lifecycle commands, stale-index rejection, canonical fallback, and typed indexed reads for large local repositories.
- **M4.x — Index refinement:** prospective measured incremental refreshes and further read-path integration without making canonical validation or mutation depend on the index.
- **M5 — Web submission and moderation infrastructure:** deferred until the local curation and dataset contracts prove stable. Prospective work belongs in a separate web repository and may include a submission API/UI, authentication, durable audit storage, and deployment safeguards.

The roadmap does not imply that development datasets are production security wordlists.
