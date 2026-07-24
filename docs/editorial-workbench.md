# Editorial Workbench

Launch the local full-screen editor with:

```bash
uv run lexiforge editor
uv run lexiforge editor --data-root ../LexiForge-Data/data
```

The selected data root follows the normal explicit option, `LEXIFORGE_DATA_ROOT`, bundled-data
precedence. The workbench does not require Git and performs no network requests.

## Layout and browsing

The header identifies the resolved repository. Filters cover free-text search, language, category,
moderation state, and release eligibility. Search matches the submitted word, its profile-normalized
form, or the exact UUID. Select column headings to sort; select the same heading again to reverse
the order. The candidate table provides Textual's scrolling and page navigation. The detail pane
shows identity, normalization, status, eligibility reasons, provenance, and recent reviews.

When a valid disposable index exists, the editor uses the backend-neutral workbench query layer for
bounded pages, search, filters and dashboard reads. Candidate details, provenance and reviews load
only for the selected row. Missing, stale, corrupt or incompatible indexes select the complete
immutable canonical snapshot fallback. `Ctrl-R` explicitly validates and reloads changed repository
files; `Alt-Left`/`Alt-Right` navigate pages, and `Ctrl-Home`/`Ctrl-End` jump to the first/last page.

## Editorial workflow

All forms produce existing immutable M3.1 operation objects. Selecting **Preview** calls
`EditorialService.preview()` and displays the existing deterministic text renderer. Nothing is
written until the validated preview is applied with `Ctrl-A` or `Ctrl-Enter`.

- `a` adds a candidate and linked provenance.
- `e` edits policy-permitted candidate fields; immutable fields are not shown.
- `r` records approval, rejection, needs-review state, criteria, and flags.
- `p` displays provenance history and can add an assertion.
- `w` prepares an audited withdrawal.
- `s` resolves a replacement by UUID or exact language-scoped word and prepares supersession.

Actor identifiers and offset-aware ISO 8601 timestamps are explicit. The application never reads
identity from Git or the operating system and never chooses the current clock automatically.
Provenance supersession remains unavailable under dataset schema 1.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl-F` | Focus candidate search |
| `Ctrl-R` | Validate and reload the repository |
| `Ctrl-P` | Focus the preview pane |
| `Ctrl-A`, `Ctrl-Enter` | Apply the exact pending validated change set |
| `Esc` | Close a dialog or discard an unapplied preview |
| `F1` | Open help |
| `a`, `e`, `r`, `p`, `w`, `s` | Open the corresponding editorial workflow |

Expected `EditorialError` failures are rendered in the preview or form and never expose a Python
traceback. Application revalidation, stale-state protection, atomic replacement, and rollback are
the same service behavior used by the CLI.

## Architecture

```text
Textual widgets
        ↓ typed query or operation input
WorkbenchRepositoryView → RepositoryIndex
        ↘ canonical RepositorySnapshot fallback
        ↓ mutations only
EditorialService.preview / apply → CSV dataset interface
```

The workbench contains presentation state and one selected read backend. It has no SQLite/CSV writer,
moderation transition table, normalization policy, duplicate detector, eligibility engine, or preview
formatter. After a successful mutation it switches to canonical fallback immediately; a verified
full index rebuild may reactivate indexed reads in a background worker. A future richer editor must
continue using the same boundary; see `docs/workbench-index-integration.md`.

For large-session features—dashboard, saved searches, batch review, similarity, comparison,
duplicate triage, blocklists, and statistics—see `docs/editorial-power-tools.md`.
