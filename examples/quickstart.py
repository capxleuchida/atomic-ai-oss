#!/usr/bin/env python3
"""Quickstart: store and retrieve atoms in 3 lines."""
import sys
sys.path.insert(0, "..")  # when running from examples/
from cas_server import store_atomic_object, load_atomic_object, ref_count_increment, object_count

# Store an atom
code = "def add(a, b):\n    return a + b\n"
h = store_atomic_object(code, kind="atom", name="add")
print(f"stored: {h[:12]}…")

# Retrieve it
retrieved = load_atomic_object(h)
print(f"retrieved: {retrieved!r}")

# Track reuse (idempotent store → bump counter instead)
h2 = store_atomic_object(code, kind="atom", name="add")  # same hash
count = ref_count_increment(h2)
print(f"reuse_count: {count}")

print(f"\nTotal atoms in store: {object_count():,}")
