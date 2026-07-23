# Repository index

LexiForge keeps CSV, YAML and text files as the canonical dataset. The repository index is
disposable derived state used to accelerate exact lookup, search, filtering, aggregates and
similarity candidate generation. It is never used as the only copy of candidate, provenance or
review data, and validation and editorial writes work without it.

The default SQLite index lives outside the dataset (`~/.cache/lexiforge/index`, or
`LEXIFORGE_INDEX_ROOT`). Use `--index-root` for read-only datasets or CI. A namespace derived from
the resolved repository path separates multiple repositories; metadata validity is based on
canonical file SHA-256 fingerprints, schema and profile compatibility rather than timestamps or
Git state. Authoritative metadata contains no build time or other wall-clock value.

## Lifecycle

```bash
lexiforge index status --data-root ../LexiForge-Data/data
lexiforge index build --data-root ../LexiForge-Data/data --index-root .cache/index
lexiforge index refresh --data-root ../LexiForge-Data/data
lexiforge index verify --data-root ../LexiForge-Data/data
lexiforge index clear --data-root ../LexiForge-Data/data --yes
```

Builds fingerprint canonical files before reading records and again after the temporary database is
complete. Any difference aborts the build, deletes the temporary database and preserves the
previous index. Publication requires a completion marker and `PRAGMA integrity_check` returning
exactly `ok`, followed by atomic replacement. Refresh reports `unchanged` when fingerprints match
and otherwise performs a safe full rebuild; there is no incremental indexing.

`candidates list` is the current CLI consumer. Missing, stale, corrupt and incompatible indexes
silently use the canonical loader unless `--require-index` is supplied. Search uses Python Unicode
`casefold`, filters use the same exact values, and results use candidate ID as the explicit
tie-breaker in both paths. Normalized duplicate lookup orders by candidate ID. Provenance orders by
record ID; reviews order by review time and ID; aggregate input orders by language, normalized word
and candidate ID. Release eligibility is calculated by the canonical evaluator during every build.

The workbench only displays index state; its browsing, filtering, statistics and mutations continue
to use the immutable canonical snapshot. Approval-critical duplicate checks remain complete and
canonical. The indexed similarity prefix bucket is advisory and is not wired into moderation or
the workbench exact scorer.

Build locks record a local PID. A lock is removed only when its PID is demonstrably absent.
Permission-denied process checks are treated as active ownership. Malformed locks and PID reuse are
handled conservatively as active locks and may require manual removal; lock age is never used.

The SQLite file contains structured JSON representations of domain records, not pickles or
executable content. It may be deleted at any time and rebuilt without data loss.
