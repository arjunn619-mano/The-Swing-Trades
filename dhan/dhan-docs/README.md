# Dhan Documentation — Local Mirror

Generated: 2026-04-21 19:53:56 UTC

A complete local mirror of Dhan's API documentation, support articles, and
Python SDK reference. Use this as a persistent knowledge base across projects.

## Contents

| Folder | Contents |
|---|---|
| `api-reference/` | OpenAPI/Swagger spec + generated human-readable API reference |
| `docs/` | All docs pages from dhanhq.co/docs/v2/ |
| `sdk/` | DhanHQ-py SDK README (from GitHub) |
| `support/` | Dhan support knowledge base articles |
| `_INDEX.md` | Full table of contents |
| `_raw/` | Raw HTML cache (for debugging) |
| `_manifest.json` | Fetch state (for incremental updates) |

## Refreshing the mirror

To pick up any new Dhan docs, re-run the crawler:
```bash
python dhan_docs_crawler.py
```

Already-fetched pages are skipped (tracked in `_manifest.json`). Delete the
manifest file — or the whole folder — to force a full re-crawl.

## Stats

- Pages fetched: **53**
- Failed URLs: **1**
- OpenAPI spec captured: **yes**

Start browsing at [`_INDEX.md`](_INDEX.md).
