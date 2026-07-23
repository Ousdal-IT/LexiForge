# Performance and profiling

M4.0 introduces a standard-library SQLite derived index. It avoids repeatedly parsing all CSV
files for exact candidate lookup, normalized duplicate lookup, first-page search and basic
dashboard aggregates. Query ordering is explicit (`normalized_word`, then candidate ID), so an
index never changes deterministic output.

The current refresh policy is intentionally conservative: unchanged content is reused; any
canonical fingerprint change triggers a verified full rebuild. This is slower than a narrowly
incremental update but guarantees dependent provenance, review, eligibility and blocklist state
cannot be left stale. A future release can add measured per-file incremental updates behind the
same metadata contract.

Similarity uses deterministic candidate generation before the existing exact scorer. The browser
is advisory and may still be expensive on very large datasets; approval-critical duplicate checks
remain complete and do not use an incomplete fast mode.

For local profiling, use the standard library without adding runtime dependencies:

```bash
python -m cProfile -s cumulative -m lexiforge index build \
  --data-root ../LexiForge-Data/data --index-root /tmp/lexiforge-index
```

Performance measurements are machine-dependent. CI uses correctness and bounded smoke tests rather
than brittle wall-clock thresholds.
