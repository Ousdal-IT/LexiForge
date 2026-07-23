# Editorial CLI

M3.1 makes routine candidate, provenance, and review maintenance available through thin CLI
adapters over `EditorialService`. Commands resolve a `DatasetRepository`, build an immutable typed
operation, preview one validated `ChangeSet`, and optionally apply that exact change set. The CSV
files remain canonical, but direct editing is an advanced recovery workflow rather than the normal
path.

## Safety model

Every mutation is a dry-run unless `--apply` is present. Text output starts with `DRY RUN` or
`APPLIED`; JSON has an explicit `applied` boolean. A preview contains logical paths and hashes, not
proposed file bytes or shadow paths. Apply performs stale-state checking, shadow validation, atomic
file replacement, rollback on expected failure, and final repository validation. Multi-file
replacement is staged and rollback-capable, although ordinary filesystems do not provide a true
transaction across several files.

Actor IDs and offset-aware ISO 8601 timestamps are explicit. They are never derived from Git, the
operating system, or the current clock. New candidates start as `submitted`; scores and similarity
findings remain advisory and no command approves automatically.

## External repository example

```bash
uv run lexiforge candidates add \
  --data-root ../LexiForge-Data/data \
  --language nb --word soloppgang --category nature \
  --submitter-id editor-pgo --source-type project-created \
  --source-reference editorial-session-001 \
  --license-basis contributor-assertion --license-eligible true \
  --created-at 2026-07-22T20:00:00+02:00 \
  --comment "Independent editorial contribution."
```

Inspect the deterministic preview, then repeat the identical invocation with `--apply`. Other
candidate workflows are `candidates edit`, `candidates withdraw`, and `candidates supersede`.
Candidate identity is immutable. Withdrawal and supersession preserve the row and append review
history; supersession requires an explicit same-language replacement and never approves it.

Use `provenance show`, `provenance add`, and `review start|approve|reject|needs-review|flag` for the
linked workflow. Approval needs a criteria YAML file with every policy-required criterion set to
`yes`, eligible provenance, an acceptable license assertion, and no blocking flag or error-level
blocklist result. Review rows are append-only.

```bash
uv run lexiforge review approve CANDIDATE_ID \
  --data-root ../LexiForge-Data/data \
  --reviewer-id reviewer-001 \
  --reviewed-at 2026-07-23T19:00:00+02:00 \
  --criteria-file review.yaml
```

All mutations support `--format text|json`. Required arguments make non-interactive automation the
canonical M3.1 path; `--non-interactive` is accepted by candidate add/edit for explicit scripting.
Line prompting is reserved for the future terminal editor.

## Schema and recovery limits

Dataset schema 1 has no provenance status or supersession link. `provenance supersede` therefore
fails clearly instead of rewriting an old assertion or inventing a schema extension. Add a new
provenance assertion when appropriate and retain the old history; a versioned schema migration is
needed for formal provenance supersession.

If preview validation fails, correct the input and retry. If stale-state protection fails, inspect
the repository diff and regenerate the preview. Applied mutations do not stage, commit, or push
Git changes; maintainers should validate and review `git diff -- data/...` themselves.

The editorial Python API is pre-1.0. UIs should import operations from `lexiforge.editorial`, never
CLI parser or prompt code. A future terminal editor should only collect input and render service
results.
