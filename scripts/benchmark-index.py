#!/usr/bin/env python3
"""Small offline benchmark for the disposable repository index."""

import argparse
import json
import time
from pathlib import Path

from lexiforge.index import RepositoryIndex, RepositoryIndexBuilder
from lexiforge.index.storage import index_path
from lexiforge.repository import DatasetRepository


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--index-root", type=Path, required=True)
    args = parser.parse_args()
    repository = DatasetRepository(args.data_root)
    started = time.perf_counter()
    metadata = RepositoryIndexBuilder(repository, args.index_root).build()
    build_seconds = time.perf_counter() - started
    started = time.perf_counter()
    with RepositoryIndex.open(repository, index_path(repository.root, args.index_root)) as index:
        count = index.count_candidates()
        first_page = index.search_candidates(limit=50).items
        dashboard = index.get_dashboard_statistics()
    query_seconds = time.perf_counter() - started
    print(
        json.dumps(
            {
                "candidates": count,
                "indexed_records": metadata.record_counts,
                "first_page": len(first_page),
                "dashboard": dashboard,
                "build_seconds": round(build_seconds, 6),
                "warm_query_seconds": round(query_seconds, 6),
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
