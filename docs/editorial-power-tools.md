# Editorial power tools

M3.3 extends `lexiforge editor` for large local curation sessions. The workbench keeps one
immutable repository snapshot for browsing and refreshes it only on `Ctrl-R` or after a successful
apply. Session and saved-search files live outside the dataset root.

## Dashboard and statistics

The workbench opens with candidate, review, approval, release, provenance, duplicate-warning, and
blocklist counters. `x` opens deterministic repository statistics. The same statistics object can be
rendered as JSON or CSV by Python consumers; it includes languages, categories, statuses, license
distribution, contributor/reviewer counts, and average review time.

## Filtering and saved searches

Filters combine language, category, status, release eligibility, source type, review state,
contributor, reviewer, license state, and blocklist state. `CandidateFilter` is a pure read model,
so adding a filter never changes validation or moderation behavior. `SavedSearchStore` persists named
filters in editor configuration (`LEXIFORGE_EDITOR_STATE` can select a test or portable location),
never in canonical data.

## Batch editing

Select rows with `Space`, then use batch review. Approval exposes every field of the canonical
`ReviewCriteria` model; every required criterion must be explicitly `yes`, just as for a single
candidate. The operation planner creates one immutable `ChangeSet` for all selected candidates.
The service validates every candidate independently before any write. If one candidate fails, the
preview reports its candidate ID and reason and the complete batch is rejected. A successful batch
appends one review record per candidate, preserving prior history, and applies all candidate/review
files atomically with rollback. Reject, needs-review, and flag actions retain their normal reason,
actor, timestamp, and flag requirements. Import review mode (`v`) narrows the browser to imported
submitted candidates for rapid triage.

## Similarity and duplicates

`i` opens the similarity browser with a deterministic distance threshold. `u` opens the duplicate
resolution assistant. Similarity findings are advisory and never approve, reject, withdraw, or
supersede automatically. `c` compares exactly two selected candidates and highlights differences in
word, normalization, category, status, eligibility, provenance, and review history. Final actions
continue through the ordinary service-backed operation forms.

## Blocklists

`b` opens the blocklist operation form. Add, edit, and disable proposals are normalized and checked
by `EditorialService.preview()` before apply. Disable entries are retained as comments in the
line-based schema, preserving an audit-visible reason while making the entry inactive. Metadata is
never rewritten by the editor. Schema and licensing rules remain those of the repository validator.

## Session and performance

The workbench persists repository, filters, sort order, and selected candidate outside the dataset.
No state file is written into `data/`. Filtering and search are in-memory operations over the
snapshot; similarity is calculated only when its browser is opened. This keeps ordinary browsing
responsive for large repositories, while an all-pairs similarity view remains an explicitly
expensive operation.

All writes—single, batch, review, provenance, and blocklist—still use `EditorialService`. The
workbench has no CSV writer and no second moderation or eligibility implementation. Similarity is
computed on demand; all-pairs analysis can be expensive for very large repositories.
