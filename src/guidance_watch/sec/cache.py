"""Content-addressed HTTP response cache on disk + SQLite metadata."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class CacheHit:
    cache_key: str
    path: Path
    content_hash: str
    status_code: int
    body: bytes


class ResponseCache:
    def __init__(self, cache_dir: Path, conn: sqlite3.Connection) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.conn = conn

    @staticmethod
    def key_for(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def get(self, url: str) -> CacheHit | None:
        cache_key = self.key_for(url)
        row = self.conn.execute(
            "SELECT cache_key, status_code, content_hash, path FROM http_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row is None:
            return None
        path = Path(row["path"])
        if not path.is_file():
            return None
        body = path.read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        if digest != row["content_hash"]:
            return None
        return CacheHit(
            cache_key=row["cache_key"],
            path=path,
            content_hash=row["content_hash"],
            status_code=int(row["status_code"] or 200),
            body=body,
        )

    def put(self, url: str, *, status_code: int, body: bytes) -> CacheHit:
        cache_key = self.key_for(url)
        content_hash = hashlib.sha256(body).hexdigest()
        path = self.cache_dir / content_hash[:2] / content_hash
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(body)
        self.conn.execute(
            """
            INSERT INTO http_cache (cache_key, url, status_code, content_hash, path, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                status_code = excluded.status_code,
                content_hash = excluded.content_hash,
                path = excluded.path,
                fetched_at = excluded.fetched_at
            """,
            (
                cache_key,
                url,
                status_code,
                content_hash,
                str(path),
                datetime.now(UTC).isoformat(),
            ),
        )
        self.conn.commit()
        return CacheHit(
            cache_key=cache_key,
            path=path,
            content_hash=content_hash,
            status_code=status_code,
            body=body,
        )
