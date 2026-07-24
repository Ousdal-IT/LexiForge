"""Deterministic similarity candidate generation and bounded result caching."""

import hashlib
import json
import sqlite3
from dataclasses import dataclass

ALGORITHM_VERSION = "1"


def canonical_pair(candidate_a: str, candidate_b: str) -> tuple[str, str]:
    ordered = sorted((candidate_a, candidate_b))
    return ordered[0], ordered[1]


def cache_key(
    candidate_a: str,
    normalized_a: str,
    candidate_b: str,
    normalized_b: str,
    threshold: int,
) -> str:
    left, right = sorted(((candidate_a, normalized_a), (candidate_b, normalized_b)))
    payload = json.dumps(
        {"algorithm": ALGORITHM_VERSION, "left": left, "right": right, "threshold": threshold},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SimilarityCacheEntry:
    key: str
    result_json: str


class SimilarityCache:
    """Small SQLite-backed cache; cached results are disposable and never authoritative."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS similarity_cache "
            "(cache_key TEXT PRIMARY KEY, candidate_a TEXT NOT NULL, candidate_b TEXT NOT NULL, "
            "algorithm TEXT NOT NULL, result_json TEXT NOT NULL)"
        )

    def get(self, key: str) -> SimilarityCacheEntry | None:
        row = self.connection.execute(
            "SELECT cache_key, result_json FROM similarity_cache WHERE cache_key=?", (key,)
        ).fetchone()
        return SimilarityCacheEntry(row[0], row[1]) if row else None

    def put(self, key: str, candidate_a: str, candidate_b: str, result_json: str) -> None:
        left, right = canonical_pair(candidate_a, candidate_b)
        self.connection.execute(
            "INSERT OR REPLACE INTO similarity_cache "
            "(cache_key,candidate_a,candidate_b,algorithm,result_json) VALUES (?,?,?,?,?)",
            (key, left, right, ALGORITHM_VERSION, result_json),
        )
        self.connection.commit()

    def invalidate_candidates(self, candidate_ids: set[str]) -> int:
        if not candidate_ids:
            return 0
        clauses = " OR ".join("candidate_a=? OR candidate_b=?" for _ in candidate_ids)
        values = [
            value
            for candidate_id in sorted(candidate_ids)
            for value in (candidate_id, candidate_id)
        ]
        cursor = self.connection.execute(f"DELETE FROM similarity_cache WHERE {clauses}", values)
        self.connection.commit()
        return cursor.rowcount


__all__ = ["SimilarityCache", "SimilarityCacheEntry", "ALGORITHM_VERSION", "cache_key"]
