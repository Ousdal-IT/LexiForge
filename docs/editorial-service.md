# Editorial service architecture

M3.0 introduces `lexiforge.editorial` as the reusable business-logic boundary for future CLI, terminal, and desktop editors. It has no rendering framework, prompts, database, network behavior, or UI dependency. Future UI code supplies operation objects and consumes structured changesets; it never writes repository CSV files directly.

## Responsibilities

`EditorialService` receives an already resolved `DatasetRepository`. It coordinates repository loading, normalization helpers, language-scoped duplicate checks, operation planning, preview, existing repository and candidate validators, release-eligibility impact, stale-state protection, atomic application, and rollback. It does not infer a repository topology or distinguish bundled data from an external `LexiForge-Data` checkout.

Existing `DatasetRepository`, profile, candidate, curation, blocklist, provenance, review, and structural validators remain authoritative. The editorial layer composes them and does not reproduce their rules.

## Lifecycle

1. Resolve and validate a `DatasetRepository`.
2. Construct `EditorialService(repository)`.
3. Pass an immutable operation object to `service.preview(operation)`.
4. The operation returns structured proposed full-file content and record identifiers.
5. The service checks paths, UTF-8, final newlines, and stale-state hashes.
6. It copies the repository to an isolated shadow root, applies the proposals there, and runs existing validators.
7. It returns an immutable, deterministic `ChangeSet` without modifying source data.
8. A caller may render the changeset as deterministic text or JSON.
9. `service.apply(changeset)` verifies the source hashes again, revalidates a fresh shadow, and atomically replaces affected text files.
10. If replacement or final validation fails, already replaced files are restored atomically.

## ChangeSet

`ChangeSet` is a frozen dataclass containing a content-derived ID, resolved repository root, operation name, sorted file changes and hashes, added/modified/superseded record IDs, warnings, validation status, and per-language release-eligibility impact. Full proposed bytes are retained for safe later application but are intentionally excluded from preview rendering. No volatile time or rendered UI text is stored.

Changesets are repository-state-specific. Any affected file whose existence or SHA-256 changes after preview causes `RepositoryStateError`; callers must preview again.

## Operations and previews

`EditorialOperation` is a typed protocol. An operation receives an editorial context with read, normalization, and duplicate-query helpers and returns an immutable `OperationPlan`. M3.0 reserves typed shells for add-candidate, edit-candidate, review, and provenance operations; their business behavior belongs to M3.1.

Preview helpers render stable plain text and key-sorted JSON. Rendering is separate from the service and model, allowing future Textual and PySide6 clients to present the same changeset without owning mutation logic.

## Error model

Expected failures use `EditorialError` subclasses: editorial `ValidationError`, `DuplicateCandidateError`, `RepositoryStateError`, and `MutationRejectedError`. UIs should catch these errors and present their actionable message without exposing an implementation traceback.

