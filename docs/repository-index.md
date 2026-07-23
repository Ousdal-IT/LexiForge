# Repository index

LexiForge keeps CSV, YAML and text files as the canonical dataset. The repository index is
disposable derived state used to accelerate exact lookup, search, filtering, aggregates and
similarity candidate generation. It is never used as the only copy of candidate, provenance or
review data, and validation and editorial writes work without it.

The default SQLite index lives outside the dataset (`~/.cache/lexiforge/index`, or
`LEXIFORGE_INDEX_ROOT`). Use `--index-root` for read-only datasets or CI. A namespace derived from
the resolved repository path separates multiple repositories; metadata validity is based on
canonical file SHA-256 fingerprints, schema and profile compatibility rather than timestamps or
Git state.

## Lifecycle

```bash
lexiforge index status --data-root ../LexiForge-Data/data
lexiforge index build --data-root ../LexiForge-Data/data --index-root .cache/index
lexiforge index refresh --data-root ../LexiForge-Data/data
lexiforge index verify --data-root ../LexiForge-Data/data
lexiforge index clear --data-root ../LexiForge-Data/data --yes
```

Builds use a temporary SQLite file, integrity verification, a completion marker and atomic
replacement. A failed build leaves the previous valid index intact. Refresh reports `unchanged`
when fingerprints match and otherwise performs a safe full rebuild; this conservative fallback
prevents stale dependent eligibility or blocklist rows. Canonical mutations remain successful if a
later derived-index rebuild fails, and the next status check rejects the stale index.

The workbench displays the index state but remains usable with canonical fallback. Approval-critical
duplicate checks continue to use complete canonical semantics. Similarity candidate generation is
an advisory prefix-bucket optimization; exact similarity scoring and moderation rules are not
changed.

The SQLite file contains structured JSON representations of domain records, not pickles or
executable content. It may be deleted at any time and rebuilt without data loss.
