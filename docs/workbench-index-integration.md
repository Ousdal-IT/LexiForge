# Textual workbench index integration

v0.7.0 gives the Textual workbench two interchangeable read backends:

```text
Textual widgets → WorkbenchRepositoryView → RepositoryIndex
                                      ↘ canonical RepositorySnapshot fallback
```

`workbench/query.py` owns the typed, backend-neutral contract. Textual code receives bounded
`CandidatePage` values and full `CandidateView` details only for the selected candidate. It never
opens SQLite, executes SQL, reads CSV files or duplicates normalization, eligibility or filtering
rules.

## Backend selection

At startup the workbench verifies the repository index. A valid index is reported as `Indexed`.
Missing, stale, corrupt and incompatible indexes produce `Canonical fallback` with a concise
diagnostic and never prevent editorial access. The detailed state remains available through
`lexiforge index status`.

Candidate pages are limited to 50 rows (the query contract allows at most 200), and page navigation
uses Alt-Left/Alt-Right, Ctrl-Home and Ctrl-End. Search and all existing filter dimensions reset
the page to the first valid page. Sorting has explicit deterministic tie-breakers.

Dashboard statistics, provenance, reviews, normalized duplicate lookup and selected-candidate
similarity candidates use the selected backend. The workbench similarity view remains advisory;
exact duplicate and approval decisions remain canonical and human-reviewed.

## Mutations and rebuilds

Every mutation still uses `EditorialService.preview()` and `EditorialService.apply()`. Immediately
after a successful apply, the workbench closes the old index handle, switches to a canonical
snapshot and refreshes the list, details and dashboard. A full verified index rebuild runs in a
Textual worker; a successful build switches the workbench back to `Indexed`. A failed build leaves
the canonical fallback active and does not undo the canonical mutation.

The build worker is generation-aware. Results from an obsolete repository generation or a disposed
screen are ignored, so an older indexed result cannot overwrite newer canonical state.

## Limitations

The workbench does not perform incremental indexing, filesystem watching or background daemons.
The canonical fallback intentionally materializes one immutable snapshot for correctness. The
indexed path avoids that full candidate-list snapshot for browsing, search, filters, statistics and
details, but advisory similarity candidate generation remains bounded by the disposable index API.
