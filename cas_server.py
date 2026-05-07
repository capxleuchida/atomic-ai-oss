#!/usr/bin/env python3
"""
cas_server.py — Content-Addressable Storage for Atomic Forge

Stores forged atoms + Golden Log patches as immutable, hash-addressed blobs.
Modeled after git's object store — write once, address by SHA256 forever.

Layout:
    atomic-library/forge/
        objects/<hash[0:2]>/<hash>.py   ← immutable code blobs
        manifests/<name>.json            ← named groups of hashes
        ref_count.db                     ← SQLite usage counter

Functions:
    store_atomic_object(code) -> hash       # dedupe + write
    manifest_create(name, hashes) -> path
    ref_count_increment(hash)
    ref_count_top(n) -> [(hash, count)]
    object_count() / manifest_count()

SPEC: cockpit/inbox/T0.md (Atomic Forge dispatch · 2026-05-05)
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Tuple, Optional

FORGE_ROOT = Path(__file__).parent
OBJECTS_DIR = FORGE_ROOT / "objects"
MANIFESTS_DIR = FORGE_ROOT / "manifests"
REF_COUNT_DB = FORGE_ROOT / "ref_count.db"

JST = timezone(timedelta(hours=9))


# ── DB bootstrap ───────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    OBJECTS_DIR.mkdir(parents=True, exist_ok=True)
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(REF_COUNT_DB))
    c.execute("""
        CREATE TABLE IF NOT EXISTS ref_count (
            hash TEXT PRIMARY KEY,
            count INTEGER NOT NULL DEFAULT 0,
            first_seen TEXT,
            last_seen TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS objects_meta (
            hash TEXT PRIMARY KEY,
            kind TEXT,                -- 'atom' | 'patch' | 'manifest'
            name TEXT,
            size_bytes INTEGER,
            created_at TEXT
        )
    """)
    c.commit()
    return c


# ── Object store ──────────────────────────────────────────────────────────────

def store_atomic_object(code: str, kind: str = "atom", name: str = "") -> str:
    """Write code as immutable blob; return SHA256 hex digest.

    Dedupes on hash — re-storing the same code is a no-op + no-error.
    Updates objects_meta with kind / name on first store.
    """
    if not isinstance(code, str):
        raise TypeError("code must be str")
    h = hashlib.sha256(code.encode("utf-8")).hexdigest()
    shard_dir = OBJECTS_DIR / h[0:2]
    shard_dir.mkdir(parents=True, exist_ok=True)
    blob_path = shard_dir / f"{h}.py"

    if not blob_path.exists():
        blob_path.write_text(code, encoding="utf-8")
        c = _conn()
        try:
            c.execute(
                "INSERT OR IGNORE INTO objects_meta(hash, kind, name, size_bytes, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (h, kind, name, len(code.encode("utf-8")), datetime.now(JST).isoformat()),
            )
            c.execute(
                "INSERT OR IGNORE INTO ref_count(hash, count, first_seen, last_seen) "
                "VALUES (?, 0, ?, ?)",
                (h, datetime.now(JST).isoformat(), datetime.now(JST).isoformat()),
            )
            c.commit()
        finally:
            c.close()
    return h


def load_atomic_object(h: str) -> Optional[str]:
    """Read code by hash; None if missing."""
    blob_path = OBJECTS_DIR / h[0:2] / f"{h}.py"
    if not blob_path.exists():
        return None
    return blob_path.read_text(encoding="utf-8")


# ── Manifests ─────────────────────────────────────────────────────────────────

def manifest_create(name: str, atom_hashes: List[str], meta: Optional[dict] = None) -> str:
    """Create a named manifest grouping a list of object hashes.

    Returns the manifest file path (string).
    """
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = name.replace("/", "_").replace(" ", "_")
    path = MANIFESTS_DIR / f"{safe_name}.json"
    payload = {
        "name": name,
        "created_at": datetime.now(JST).isoformat(),
        "object_count": len(atom_hashes),
        "objects": atom_hashes,
        "meta": meta or {},
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def manifest_load(name: str) -> Optional[dict]:
    safe_name = name.replace("/", "_").replace(" ", "_")
    path = MANIFESTS_DIR / f"{safe_name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ── Ref-count ─────────────────────────────────────────────────────────────────

def ref_count_increment(h: str, by: int = 1) -> int:
    """Bump usage counter for hash; return new count.

    Idempotent on missing rows (auto-inserts at count=by).
    """
    now = datetime.now(JST).isoformat()
    c = _conn()
    try:
        c.execute(
            "INSERT INTO ref_count(hash, count, first_seen, last_seen) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(hash) DO UPDATE SET count = count + ?, last_seen = ?",
            (h, by, now, now, by, now),
        )
        c.commit()
        row = c.execute("SELECT count FROM ref_count WHERE hash = ?", (h,)).fetchone()
        return int(row[0]) if row else 0
    finally:
        c.close()


def ref_count_top(n: int = 5) -> List[Tuple[str, int]]:
    c = _conn()
    try:
        rows = c.execute(
            "SELECT hash, count FROM ref_count ORDER BY count DESC, hash ASC LIMIT ?",
            (n,),
        ).fetchall()
        return [(r[0], int(r[1])) for r in rows]
    finally:
        c.close()


# ── Stats ─────────────────────────────────────────────────────────────────────

def object_count() -> int:
    """Count files under objects/ (lower bound; truth is the filesystem)."""
    if not OBJECTS_DIR.exists():
        return 0
    return sum(1 for _ in OBJECTS_DIR.rglob("*.py"))


def manifest_count() -> int:
    if not MANIFESTS_DIR.exists():
        return 0
    return sum(1 for _ in MANIFESTS_DIR.glob("*.json"))


def list_objects(limit: int = 50) -> List[dict]:
    c = _conn()
    try:
        rows = c.execute(
            "SELECT hash, kind, name, size_bytes, created_at FROM objects_meta "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"hash": r[0], "kind": r[1], "name": r[2], "size_bytes": r[3], "created_at": r[4]}
            for r in rows
        ]
    finally:
        c.close()


# ── CLI smoke ─────────────────────────────────────────────────────────────────

def _smoke() -> int:
    code = "def hello():\n    return 'world'\n"
    h1 = store_atomic_object(code, kind="atom", name="hello")
    h2 = store_atomic_object(code, kind="atom", name="hello")  # dedupe path
    assert h1 == h2, "dedupe must return same hash"
    n = ref_count_increment(h1)
    n2 = ref_count_increment(h1)
    assert n2 == n + 1, f"counter must increment ({n} -> {n2})"
    mp = manifest_create("smoke_test", [h1])
    print(f"smoke OK · hash={h1[:12]} count={n2} manifest={mp}")
    print(f"object_count={object_count()} manifest_count={manifest_count()}")
    print(f"top5={ref_count_top(5)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--smoke":
        sys.exit(_smoke())
    print("Usage: python3 cas_server.py --smoke")
