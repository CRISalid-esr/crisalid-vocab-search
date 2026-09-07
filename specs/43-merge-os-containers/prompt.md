# Issue #43 — Merge OS containers

> Specification for the `43-merge-os-containers` branch.
> GitHub issue: https://github.com/CRISalid-esr/crisalid-vocab-search/issues/43

## Goal

The one-OpenSearch-container-per-vocabulary design consumes too much RAM: every
container runs its own JVM, each auto-sizing its heap. Replace the N per-vocab
containers with a **single OpenSearch container embedding all vocabularies**,
one index per vocabulary. The REST API surface (endpoints, parameters, response
shapes) must not change.

## Context (current state)

- Each vocabulary ships as its own image, built from `os-vocabs/docker/Dockerfile`
  with `--build-arg CONCEPTS_SRC=os-vocabs/build/<vocab>/concepts.ndjson.gz`.
- `entrypoint.sh` loads the single NDJSON into physical index `concepts_v1`
  behind alias `concepts`.
- `LocalOpenSearchVocabProxy` hardcodes the `concepts` alias in its URLs
  (`app/services/proxies/local_opensearch.py`); one proxy per vocabulary, each
  pointing to a distinct host:port (`vocab_config.yaml` ports 9200–9206,
  `vocab_config_docker.yaml` service hostnames).
- CI (`cd_push_os.yaml`, `cd_release.yaml`) builds and pushes one image per
  vocabulary via a build matrix.
- The prebuilt `concepts.ndjson.gz` files for all 6 vocabularies (jel, acm,
  aat, elsst, pactols, euroscivoc) are committed under `os-vocabs/build/`.

## Specification

### 1. Single multi-vocabulary OpenSearch image (`os-vocabs/`)

- **Build-time vocabulary selection**: replace the `CONCEPTS_SRC` build-arg with
  a `VOCABS` build-arg holding the list of embedded vocabularies
  (e.g. `--build-arg VOCABS="jel,acm,aat,elsst,pactols,euroscivoc"`).
  - **Default = all vocabularies** present under `os-vocabs/build/`: users
    pulling the official image from Docker Hub get everything; users who want a
    subset rebuild locally with a shorter list.
  - The Dockerfile copies the selected `os-vocabs/build/<vocab>/concepts.ndjson.gz`
    files into the image (e.g. under `/data/<vocab>/`).
- **Index layout**: one index per vocabulary — physical index
  `concepts_<vocab>_v1` behind alias `concepts_<vocab>` (e.g. `concepts_jel`).
  Same versioned-index + alias pattern as today, namespaced per vocab.
- **entrypoint.sh**: loop over the embedded vocabularies; for each, if its alias
  is missing, create `concepts_<vocab>_v1` with the shared
  `os-vocabs/index/settings.json` + `mappings.body.json`, bulk-load its NDJSON,
  refresh, and add the alias. Failures for one vocabulary must not kill the
  container nor block the other vocabularies (keep the current tolerant,
  idempotent behavior).
- **Heap defaults**: set an explicit default JVM heap in the image
  (e.g. `OPENSEARCH_JAVA_OPTS=-Xms1g -Xmx1g`), overridable via environment at
  run time. Without this, the single JVM still auto-sizes to ~50% of host RAM.

### 2. API changes (`app/`)

- `LocalOpenSearchVocabProxy`: stop hardcoding the `concepts` alias. The index
  queried for a vocabulary is **derived from its identifier**
  (`concepts_<identifier>`), with an **optional `index` key** in the
  vocab_config entry to override it. Applies to both `autocomplete` and `probe`
  URL building.
- `VocabService` keeps its structure: one proxy per configured vocabulary,
  asyncio fan-out (`asyncio.gather`), merge/sort/dedup logic unchanged. Proxies
  now happen to share the same host:port and differ only by index.
- `vocab_config.yaml` (local dev): all entries point to `http://localhost:9200`.
- `vocab_config_docker.yaml`: all entries point to the single `os` service
  (`http://os`, port 9200).
- No route, parameter, or response-model changes. `/vocabs` must return the
  same per-vocabulary `identifier`, `languages`, `doc_count`, `status` as
  before (probing per index now).

### 3. docker-compose

- Replace the `os-jel` … `os-euroscivoc` services with a single `os` service
  using the merged image, exposing 9200 (host port mapping commented out, as
  today).
- `api` service depends on `os` only.

### 4. CI / CD

- `cd_push_os.yaml`: drop the build matrix; build and push **one** image with
  tags `${DOCKERHUB_REPO}:os-${DEV_LINE}-dev` and `${DOCKERHUB_REPO}:os-dev`
  (single buildcache ref).
- `cd_release.yaml` (`os-bundles` job): same — single image, tags
  `os-<version>`, `os-<minor>`, `os-<major>`, `os-latest`.
- Per-vocabulary images are **no longer built or pushed**.

### 5. Documentation

- Rewrite README sections 4 ("Building and running") and 5 ("Adding a new
  vocabulary"): single image build with `VOCABS` build-arg, subset rebuild
  example, updated local-testing flow (run the merged container with
  `-p 9200:9200`, `APP_ENV=DEV uv run python -m app.main`). Adding a vocabulary
  no longer requires editing CI matrices — only `os-vocabs/build/`, the two
  vocab_config files, and the default `VOCABS` list if it is not dynamic.
- Update `CLAUDE.md` accordingly.

### 6. Tests

- Adapt existing proxy/service tests to the derived index name
  (`concepts_<vocab>` in mocked URLs) and add coverage for the optional
  `index` config override.
- Keep the strict-respx, no-real-HTTP testing approach.

## Out of scope

- The `/search` endpoint (still not implemented).
- MeSH and other not-yet-loaded vocabularies.
- Single-index-with-`vocab`-field design (rejected: keep one index per vocab).
- Backward compatibility with the old per-vocabulary images.
- Remote (non-local_os) proxy types.

## Acceptance criteria

1. `docker build -f os-vocabs/docker/Dockerfile .` (no build-arg) produces an
   image containing all 6 vocabularies; `--build-arg VOCABS="jel,acm"` produces
   one with only those two.
2. Starting the merged container creates one `concepts_<vocab>` alias per
   embedded vocabulary, each fully loaded (doc counts match the old per-vocab
   images).
3. `docker-compose up -d` runs exactly two containers (os + api);
   `GET /api/v1/vocabs/` lists every embedded vocabulary with correct
   `languages` and `doc_count`.
4. `/autocomplete` responses are identical to the pre-merge behavior (same
   shape, same results for the same data).
5. RAM footprint: a single OpenSearch JVM with a bounded default heap replaces
   the previous one-JVM-per-vocabulary layout.
6. `APP_ENV=TEST uv run pytest` and `pylint --rcfile=.pylintrc app/` pass.
7. CI pushes a single `os-*` image instead of six.
