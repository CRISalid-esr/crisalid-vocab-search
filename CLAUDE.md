# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Machine-specific paths (deployment stack, client apps, mockups) belong in `CLAUDE.local.md` (not committed). See `CLAUDE.local.sample.md` for the expected entries.

## Commands

Dependencies are managed with `uv` (`uv sync` installs main + dev groups).

```bash
# Run all tests (APP_ENV=TEST is also set in tests/conftest.py, but CI passes it explicitly)
APP_ENV=TEST uv run pytest

# Run a single test file / test
APP_ENV=TEST uv run pytest tests/services/proxies/test_local_opensearch_proxy_autocomplete.py
APP_ENV=TEST uv run pytest tests/services/test_vocab_service.py -k <test_name>

# Lint (same invocation as CI)
uv run pylint --rcfile=.pylintrc app/

# Run the API locally against local vocab containers (uses vocab_config.yaml)
APP_ENV=DEV uv run python -m app.main   # serves on port 8002; docs at /docs
```

After changing dependencies with `uv add` / `uv add --dev`, re-export the requirements files (used by Docker and CI):

```bash
uv export --format requirements-txt --no-annotate --no-hashes --no-header --no-group dev -o requirements.txt
uv export --format requirements-txt --no-annotate --no-hashes --no-header --group dev -o requirements-dev.txt
```

### Docker

```bash
# Convert a SKOS vocabulary to the index format (NDJSON)
python3 os-vocabs/loaders/load_skos.py \
  --in os-vocabs/thesauri/<vocab>/<date>/<file> \
  --out os-vocabs/build/<vocab>/concepts.ndjson.gz \
  --scheme <SCHEME>

# Build the multi-vocabulary OpenSearch image (run from repo root; default = all vocabs)
docker build -f os-vocabs/docker/Dockerfile -t crisalid-vocab-search:os-0.1 .
# Subset build:
docker build -f os-vocabs/docker/Dockerfile --build-arg VOCABS="jel,acm" -t crisalid-vocab-search:os-subset-0.1 .

# Build the API image (bakes vocab_config_docker.yaml in as vocab_config.yaml)
docker build -t crisalid-vocab-search:api-0.1 .

# Full stack
docker compose up -d   # Compose v2 plugin (not legacy docker-compose); API on http://localhost:8000/docs
```

## Architecture

Two deliverables:

1. **A single multi-vocabulary OpenSearch container** (`os-vocabs/`): embeds OpenSearch 3 plus all pre-indexed thesauri, one index per vocabulary. The embedded set is selected at build time via `--build-arg VOCABS="jel,acm,..."` (default: all under `os-vocabs/build/`); a bounded default JVM heap is set via `OPENSEARCH_JAVA_OPTS` (overridable at run time). All vocabularies share the same index schema (`os-vocabs/index/settings.json` + `mappings.body.json`, SKOS-like: `pref`/`alt`/`description` per language, `broader`/`narrower`, flattened `search_all`; `.edge` subfields for autocomplete, folding analyzers for case/diacritic-insensitive matching). `docker/entrypoint.sh` starts OpenSearch and, for each vocabulary in `/data/vocabs.list`, creates index `concepts_<vocab>_v1` behind alias `concepts_<vocab>` and bulk-loads `/data/<vocab>/concepts.ndjson.gz` on first boot (per-vocab failures don't block the others). `loaders/load_skos.py` converts SKOS RDF into that NDJSON format; non-SKOS vocabularies need a custom loader producing the same structure.

2. **FastAPI frontend** (`app/`): unified REST API over all vocab containers.
   - `app/vocab_search.py` defines the `VocabSearch` FastAPI app; `app.main:app` is the uvicorn entry point.
   - **Settings** (`app/config.py` + `app/settings/`): `APP_ENV` (`DEV`/`PROD`/`TEST`, default `PROD`) selects the settings class. Each environment loads its vocabulary config at import time: dev/prod use root `vocab_config.yaml` (Docker image overwrites it with `vocab_config_docker.yaml`), tests use `tests/vocab_config.yaml`. Route prefix is `{api_prefix}/{api_version}` — `/api/v1` in practice (`API_VERSION=v1` from `.env`; code default is `v0`).
   - **Routes** (`app/routes/`): `/vocabs`, `/autocomplete`, `/search` (search not yet implemented), plus `/health`. Routes parse CSV params (`app/utils/parameters.py`) and delegate to `VocabService`.
   - **Service/proxy layer**: `VocabService` (`app/services/vocab_service.py`) builds one proxy per configured vocabulary from `_TYPE_REGISTRY` (config `type` → proxy class; currently only `local_os` → `LocalOpenSearchVocabProxy`). Queries fan out concurrently to all selected proxies, then results are merged, sorted by score, and deduplicated by IRI. Each `local_os` proxy queries index `concepts_<identifier>` by default; an optional `index` key in the vocab config entry overrides it. Proxies (`app/services/proxies/`) implement `_validate_cfg`, `probe`, and `autocomplete` per the `VocabProxy` ABC; they must swallow their own network errors (return `UNAVAILABLE` status / empty results rather than raise). New backend types are added by implementing the ABC and registering in `_TYPE_REGISTRY`.
   - **Models** (`app/models/`): pydantic response models (`Concept`, `SearchResults`, `Vocabulary`); `/search` and `/autocomplete` share the same response shape.

## Tests

Tests never touch real backends: an autouse strict `respx` router (`tests/conftest.py`) makes any unmocked HTTP request fail. OpenSearch responses are mocked from JSON fixtures in `tests/fixtures/data/os/`, with fixture helpers in `tests/fixtures/`. Request the `http_mock` fixture to register routes.

## Adding a new vocabulary

Full checklist is in README section 5. Summary: raw files go in `os-vocabs/thesauri/<vocab-id>/<date>/` — but do NOT commit them: source vocabulary packages are kept out of version control for legal reasons (their licenses may not allow redistribution); only the generated `concepts.ndjson.gz` files under `os-vocabs/build/` are versioned. Convert to `os-vocabs/build/<vocab-id>/concepts.ndjson.gz`; add the vocab to the default `VOCABS` list in `os-vocabs/docker/Dockerfile`; register in `vocab_config.yaml` (local, `http://localhost:9200`) and `vocab_config_docker.yaml` (single `os` service). No CI change needed — the workflows build one image embedding everything in the default `VOCABS` list. Note: the API container only sees vocabularies present in the config baked at image build time — for local testing run the merged OS container with `-p 9200:9200` and start the API with `APP_ENV=DEV`.
