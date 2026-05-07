# Atomic AI — OSS Core

> Build better code with atoms. 1,000,000+ Python functions, quality-gated and production-ready.

**Atomic AI** is an open-source code intelligence layer that decomposes software into verified, reusable *atoms* (small, tested function units) and serves them via a content-addressable store.

## What is an Atom?

An atom is a Python function that:
- Has 3–80 lines of non-trivial code
- Passes AST validation
- Comes from permissively-licensed OSS (MIT, Apache-2.0, BSD, etc.)
- Is indexed by SHA-256 hash for O(1) deduplication

## Architecture

```
OSS Repos ──▶ textbook_extractor.py ──▶ JSONL
                                          │
                                          ▼
                                  atom_ingest_worker.py
                                    (quality gate)
                                          │
                                          ▼
                                    CAS (cas_server.py)
                                  objects/<hash[0:2]>/<hash>.py
                                          │
                                          ▼
                                  atomic_api_gateway.py
                                  /v1/forge  /v1/atoms
```

## Current Stats

| Metric | Value |
|--------|-------|
| Atoms in CAS | 268,000+ |
| OSS repos harvested | 60+ |
| Quality gate pass rate | ~95% |
| Target | 1,000,000 atoms |

## Quick Start

```bash
git clone https://github.com/capxleuchida/atomic-ai-oss.git
cd atomic-ai-oss
python3 -m pip install -r requirements.txt

# Extract from OSS repos
python3 scripts/textbook_extractor.py --repos TheAlgorithms/Python --limit 10000

# Ingest into CAS
python3 scripts/atom_ingest_worker.py --source atomic-library/data/

# Query
curl http://localhost:8080/v1/atoms?q=sort&limit=10
```

## Components

| File | Purpose |
|------|---------|
| `scripts/textbook_extractor.py` | Clone OSS repos → extract Python functions → JSONL |
| `scripts/atom_ingest_worker.py` | JSONL → quality gate → CAS insert |
| `atomic-library/forge/cas_server.py` | Content-addressable storage with SQLite index |
| `atomic_api_gateway.py` | REST API: /v1/forge /v1/atoms /v1/search |

## Quality Gate

Each atom passes through:
1. **Line length** — 3–80 non-blank lines
2. **Non-trivial body** — not just `pass` / `return None`
3. **License check** — open-licensed sources only
4. **AST validation** — valid Python syntax
5. **Secret detection** — no API keys / JWTs embedded

## License

MIT — see [LICENSE](LICENSE)

## Contributing

PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

*Built by capxle · 猫繁栄のために*
