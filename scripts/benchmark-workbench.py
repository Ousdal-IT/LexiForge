#!/usr/bin/env python3
"""Benchmark bounded workbench queries on a deterministic synthetic repository."""

import argparse
import csv
import json
import shutil
import tempfile
import time
import tracemalloc
from pathlib import Path

from lexiforge.index import RepositoryIndexBuilder
from lexiforge.models import CandidateStatus
from lexiforge.repository import DatasetRepository
from lexiforge.workbench.model import CandidateFilter
from lexiforge.workbench.query import CandidateQuery, IndexedWorkbenchView, open_workbench_view


def _extend_candidates(root: Path, count: int) -> None:
    path = root / "languages/nb/candidates.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or ())
    template = dict(rows[0])
    for number in range(1, count + 1):
        row = dict(template)
        row.update(
            {
                "id": f"90000000-0000-4000-8000-{number:012d}",
                "word": f"benchmarkword{number:06d}",
                "status": "submitted",
                "reviewed_at": "",
                "score": "",
                "notes": "deterministic benchmark candidate",
            }
        )
        rows.append(row)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--index-root", type=Path, required=True)
    parser.add_argument("--count", type=int, default=10_000)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="lexiforge-workbench-") as temporary:
        root = Path(temporary) / "data"
        shutil.copytree(args.data_root, root)
        _extend_candidates(root, args.count)
        repository = DatasetRepository(root)

        tracemalloc.start()
        started = time.perf_counter()
        canonical = open_workbench_view(repository, Path(temporary) / "missing-index")
        canonical_page = canonical.list_candidates(CandidateQuery(limit=50))
        canonical_seconds = time.perf_counter() - started
        canonical_peak = tracemalloc.get_traced_memory()[1]
        canonical.close()
        tracemalloc.stop()

        started = time.perf_counter()
        metadata = RepositoryIndexBuilder(repository, args.index_root).build()
        build_seconds = time.perf_counter() - started
        indexed = open_workbench_view(repository, args.index_root)
        if not isinstance(indexed, IndexedWorkbenchView):
            raise SystemExit("expected a valid indexed workbench backend")

        measurements: dict[str, float] = {}
        for name, query in (
            ("first_page", CandidateQuery(limit=50)),
            (
                "search",
                CandidateQuery(filters=CandidateFilter(search="BENCHMARKWORD19"), limit=50),
            ),
            (
                "filter",
                CandidateQuery(filters=CandidateFilter(status=CandidateStatus.SUBMITTED), limit=50),
            ),
        ):
            started = time.perf_counter()
            page = indexed.list_candidates(query)
            measurements[name] = time.perf_counter() - started
            if len(page.items) > 50:
                raise SystemExit(f"{name} returned an unbounded page")
        started = time.perf_counter()
        dashboard = indexed.get_dashboard_statistics()
        measurements["dashboard"] = time.perf_counter() - started
        details = indexed.get_candidate(canonical_page.items[0].candidate.id)
        if details is None:
            raise SystemExit("indexed detail lookup failed")
        indexed.close()
        print(
            json.dumps(
                {
                    "candidates": metadata.record_counts["candidates"],
                    "canonical_first_page": len(canonical_page.items),
                    "canonical_preparation_seconds": round(canonical_seconds, 6),
                    "canonical_peak_bytes": canonical_peak,
                    "index_build_seconds": round(build_seconds, 6),
                    "indexed": {key: round(value, 6) for key, value in measurements.items()},
                    "indexed_dashboard_candidates": dashboard.total_candidates,
                    "indexed_first_page_bounded": True,
                    "indexed_detail_histories": {
                        "provenance": len(details.provenance),
                        "reviews": len(details.reviews),
                    },
                },
                sort_keys=True,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
