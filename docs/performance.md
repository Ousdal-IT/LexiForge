# Performance and profiling

M4.0 introduces a standard-library SQLite derived index for selected read paths. The public typed
API supports exact candidate and normalized duplicate lookup, candidate search/filtering,
provenance, reviews, statistics and advisory similarity candidate generation. At present,
`candidates list` is the only CLI read path using it; the workbench only displays index status.

Correctness takes precedence over query speed. Candidate search performs exact SQL filters, then
uses Python `casefold` and candidate-ID ordering to match canonical fallback for all Unicode input.
Statistics return the same logical structure and values as the canonical repository snapshot.

The current refresh policy is intentionally conservative: unchanged content is reused; any
canonical fingerprint change triggers a verified full rebuild. This is slower than a narrowly
incremental update but guarantees dependent provenance, review, eligibility and blocklist state
cannot be left stale. Incremental indexing is intentionally outside M4.0.

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

## M4.0 hardening measurement

Four runs of `scripts/benchmark-index.py` were recorded on 2026-07-23 using the bundled 72-candidate
repository, Python 3.12.13 and Linux 6.6.119 x86-64. Every run verified candidate-count and complete
dashboard parity before reporting:

| Measurement | Observed range |
| --- | ---: |
| Canonical snapshot and statistics | 0.040070–1.077596 s |
| Full verified index build | 0.150864–1.175979 s |
| Validated index open, first page and statistics | 0.023893–0.215522 s |

The shared development environment produced substantial timing variance, so these measurements are
a correctness smoke benchmark rather than evidence of a stable speedup. The 2,000-record synthetic
regression test provides bounded large-repository coverage without asserting wall-clock timing.
