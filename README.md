# CRISalid Vocab Search

**CRISalid vocab search** provides two main services for research information systems (CRIS):

1. **Ready-to-use Docker containers** with [OpenSearch](https://opensearch.org/) and bundled vocabularies.
    - Each container ships with a single thesaurus preloaded.
    - This ensures uniform access across vocabularies for tasks such as concept autocomplete and agentic suggestion.

Examples of packaged vocabularies :

- JEL (Journal of Economic Literature codes)
- MeSH (Medical Subject Headings)
- ACM Computing Classification System
- Getty AAT (Art & Architecture Thesaurus)

2. **A unified REST API frontend**  
   A single [FastAPI](https://fastapi.tiangolo.com/) service acts as the entry point for client applications.  
   Instead of dealing with OpenSearch syntax, users access a simplified REST interface for:
    - **Search** (free text queries)
    - **Autocomplete** (prefix queries)

API Features

- **Vocabulary selection**: target one or more vocabularies by name. A discovery endpoint (`/vocabs`) lists what is
  available.
- **Language filtering (queries)**: restrict queries to one or more languages, or search across all.
- **Field filtering (queries)**: choose which fields to search (`pref`, `alt`, `description`, `search_all`); defaults to
  all.
- **Language filtering (responses)**: select which languages of labels/description to return.
- **Field filtering (responses)**: select which fields to display in the results; defaults to all.
- **Cross-language search**: case/diacritic folding analyzers allow matching across languages without complex query
  syntax.

---

## 1. Project goals

- **Dependency reduction**: avoid dependencies on third-party services (e.g. hosted search engines).
- **1 vocabulary per container**: each container is self-contained, embedding both OpenSearch and the pre-indexed
  thesaurus, in order to allow institutions to deploy only the vocabularies they need and reduce starting delay.
- **Uniform OpenSearch schema**: all vocabularies share the same OpenSearch mapping, ensuring consistent queries across
  vocabularies.
- **CRIS integration**: expose endpoints that support research information systems (concept lookup, autocomplete,
  cross-language search).

---

## 2. REST API (FastAPI)

### 2.1 `GET /vocabs`

Return the list of vocabularies known to the frontend.

**Response 200**

```json
{
  "items": [
    {
      "identifier": "jel",
      "languages": [
        "en",
        "fr",
        "de",
        "es"
      ],
      "doc_count": 1265
    }
  ]
}
```

---

### 2.2 `GET /search`

Free‑text search with simple parameters.

**Query parameters**

* `q` (string, required) — Search string.
* `vocabs` (csv, optional) — Comma‑separated vocabulary IDs. Example: `jel,mesh`.
* `lang` (csv, optional) — Restrict to languages. Example: `fr,en`.
* `fields` (csv, optional) — Search fields. Defaults: `pref,alt,description,search_all`.
* `display_langs` (csv, optional) — Restrict labels/descriptions to given languages.
* `display_fields` (csv, optional) — Fields to include in hits. Default: all.
* `limit` (int, optional) — Page size (default 20, max 100).
* `offset` (int, optional) — Result offset for pagination (default 0).
* `highlight` (bool, optional) — Include highlights (default: false).
* `broader`: "ids" | "full" (default "ids")
* `narrower`: "ids" | "full" (default "ids")
* `broader_depth`: integer (default 1, -1 = traverse all levels)
* `narrower_depth`: integer (default 1, -1 = traverse all levels)

**Broader/narrower options**

- "ids": return only identifiers of related concepts
- "full": return full metadata of related concepts (same fields as main hits)
Inside related concepts, broader/narrower relations are always returned as "ids" to avoid deep nesting.

**Response shape**

```json
{
  "total": 42,
  "items": [
    {
      "iri": "http://…#O43",
      "scheme": "JEL",
      "score": 9.1,
      "best_label": {
        "lang": "fr",
        "text": "O43 - Institutions et croissance",
        "source_field": "pref",
        "highlight": null
      },
      "pref": [
        {
          "lang": "fr",
          "text": "O43 - Institutions et croissance",
          "highlight": null
        },
        {
          "lang": "en",
          "value": "O43 - Institutions and Growth",
          "highlight": null
        }
      ],
      "alt": [
        {
          "lang": "fr",
          "text": "Institutions et croissance",
          "highlight": null
        },
        {
          "lang": "en",
          "text": null,
          "highlight": null
        }
      ],
      "description": [
        {
          "lang": "fr",
          "text": "...",
          "highlight": null
        }
      ],
      "broader": [
        // see broader/narrower examples below
      ],
      "narrower": [
        // see broader/narrower examples below
      ]
    }
  ]
}
```

**Broader/narrower example**

With broader=ids (default)
```json
{
  "items": [
    {
      "iri": "http://…#O43",
      "pref": {"fr": ["O43 - Institutions et croissance"]},
      "broader": ["http://…#O4"],       // IDs only
      "narrower": []                    // IDs only
    }
  ]
}
```

With broader=full :

```json
{
  "items": [
    {
      "iri": "http://…#O43",
      "best_label": {
        "lang": "fr",
        "text": "O4 - Croissance économique",
        "source_field": "pref",
        "highlight": null
      },
      "pref": [{
        "lang": "fr",
        "text": "O4 - Croissance économique",
        "highlight": null
      }],
      "broader": [                       // Full metadata
        {                               // No best_label in nested concepts
          "iri": "http://…#O4",
          "pref": [{
            "lang": "fr",
            "text": "O4 - Croissance économique",
            "highlight": null
          }],
          "broader": ["http://…#O"],     // IDs only
          "narrower": ["http://…#O43"]   // IDs only
        }
      ],
      "narrower": []                    // IDs only
    }
  ]
}
```

With narrower=full&narrower_depth=2 :

```json
{
  "items": [
    {
      "iri": "http://…#O4",
      "best_label": {
        "lang": "fr",
        "text": "O4 - Croissance économique",
        "source_field": "pref",
        "highlight": null
      },
      "pref": [{
        "lang": "fr",
        "text": "O4 - Croissance économique",
        "highlight": null
      }],
      "broader": ["http://…#O"],        // IDs only
      "narrower": [                     // Full metadata
        {                               // No best_label in nested concepts
          "iri": "http://…#O43",
          "pref": [{
            "lang": "fr",
            "text": "O43 - Institutions et croissance",
            "highlight": null
          }],
          "broader": ["http://…#O4"],   // IDs only
          "narrower": [
            {                       // Full metadata (depth=2)
                "iri": "http://…#O44",
                "pref": [{
                    "lang": "fr",
                    "text": "O44 - Environnement et croissance",
                    "highlight": null
                }],
                "broader": ["http://…#O4"],   // IDs only
                "narrower": []                 // IDs only
            }
          ]                 
        },
        {
          "iri": "http://…#O44",
          "pref": [{
            "lang": "fr",
            "text": "O44 - Environnement et croissance",
            "highlight": null
          }],
          "broader": ["http://…#O4"],   // IDs only
          "narrower": []                 // IDs only
        }
      ]
    }
  ]
}
```

**Behavior**

* Queries use a weighted multi‑match across fields (pref > alt > description).
* If `lang` is provided, query filters to that language set and targets fields like `pref.fr`. Otherwise, all languages
  are searched.

**Examples**

```bash
# Default search in all languages/fields
curl -s 'http://api.example/v1/search?q=investissement&limit=5'

# Restrict to JEL + French labels only
curl -s 'http://api.example/v1/search?q=croissance&vocabs=jel&lang=fr&fields=pref,alt&limit=5'

# Return only key metadata + FR/EN labels
curl -s 'http://api.example/v1/search?q=growth&display_fields=iri,scheme,pref&display_langs=fr,en'
```
### 2.3 `GET /autocomplete`

Prefix search for type-ahead UIs.
**Response shape is identical to `/search`** so front-end components can render the same rich cards (labels, descriptions, relations, highlights, etc.).

**Query parameters**

Same as `/search`:

* `q` (string, required) — Search string (treated as a **prefix**).
* `vocabs` (csv, optional) — Comma-separated vocabulary IDs. Example: `jel,mesh`.
* `lang` (csv, optional) — Restrict to languages. Example: `fr,en`.
* `fields` (csv, optional) — Search fields. Defaults: `pref,alt,description,search_all`.
* `display_langs` (csv, optional) — Restrict labels/descriptions to given languages.
* `display_fields` (csv, optional) — Fields to include in hits; default: all.
* `limit` (int, optional) — Page size (default 20, max 100).
* `offset` (int, optional) — Result offset for pagination (default 0).
* `highlight` (bool, optional) — Include highlights (default: false).
* `broader`: `"ids"` | `"full"` (default `"ids"`)
* `narrower`: `"ids"` | `"full"` (default `"ids"`)
* `broader_depth`: integer (default 1, `-1` = traverse all levels)
* `narrower_depth`: integer (default 1, `-1` = traverse all levels)

**Behavior**

* Performs **prefix matching** primarily on `.edge` subfields (`pref.*.edge`, `alt.*.edge`) with boosts favoring `pref`.
  Implementations may also use `bool_prefix` to improve matching quality.
* If `lang` is provided, matching is restricted to those language fields; otherwise all languages are considered.
* If `highlight=true`, highlights are returned on the base fields (e.g., `pref.fr`, `alt.en`, `description.*`) to keep markup consistent with `/search`.
* `broader`/`narrower` follow the same rules as `/search` (IDs by default; `"full"` returns related concept metadata, whose own relations are always IDs to avoid deep nesting).

**Response 200 (same structure as `/search`)**

```json
{
  "total": 3,
  "items": [
    {
      "iri": "http://…#O43",
      "scheme": "JEL",
      "score": 9.1,
      "best_label": {
        "lang": "fr",
        "text": "O43 - Institutions et croissance",
        "source_field": "pref",
        "highlight": "O43 - <em>Ins</em>titutions et croissance"
      },
      "pref": [
        {
          "lang": "fr",
          "text": "043 - Institutions et croissance",
          "highlight": "O43 - <em>Ins</em>titutions et croissance"
        },
        {
          "lang": "en",
          "value": "O43 - Institutions and Growth",
          "highlight": null
        }
      ],
      "alt": [
        {
          "lang": "fr",
          "text": "Institutions et croissance",
          "highlight": null
        },
        {
          "lang": "en",
          "text": null,
          "highlight": null
        }
      ],
      "description": [
        {
          "lang": "fr",
          "text": "…",
          "highlight": null
        }
      ],
      "broader": [
        "http://…#O4"
      ],
      "narrower": []
    },
    {
      "iri": "http://…#O44",
      "scheme": "JEL",
      "score": 8.2,
      "best_label": {
        "lang": "fr",
        "text": "O44 - Environnement et croissance",
        "source_field": "pref",
        "highlight": "O44 - <em>En</em>vironnement et croissance"
      },
      "pref": [
        {
          "lang": "fr",
          "text": "O44 - Environnement et croissance",
          "highlight": "O44 - <em>En</em>vironnement et croissance"
        },
        {
          "lang": "en",
          "text": "O44 - Environment and Growth",
          "highlight": null
        }
      ],
      "alt": [
        {
          "lang": "fr",
          "text": "Environnement et croissance",
          "highlight": null
        },
        {
          "lang": "en",
          "text": null,
          "highlight": null
        }
      ],
      "description": [
        {
          "lang": "fr",
          "text": "…",
          "highlight": null
        }
      ],
      "broader": [
        "http://…#O4"
      ],
      "narrower": []
    }
  ]
}
```


## 3. Packaged vocabularies

### 3.1 Schema overview

The schema is a **compromise**:

- It stays close to [SKOS](https://www.w3.org/TR/skos-reference/) (preferred labels, alternative labels,
  broader/narrower, definitions).
- But it also **accepts non-SKOS-compliant vocabularies**, by allowing simplified description fields and a flattened
  `search_all` field.

### Fields

| Field         | Type        | Description                                                                                   |
|---------------|-------------|-----------------------------------------------------------------------------------------------|
| `vocab`       | `keyword`   | Vocabulary name (e.g. `jel`)                                                                  |
| `identifier`  | `keyword`   | Unique identifier within the vocabulary (e.g. `O43`)                                          |
| `iri`         | `keyword`   | Full IRI of the concept (e.g. `http://zbw.eu/beta/external_identifiers/jel#O43`) if available |
| `top_concept` | `boolean`   | Whether it is a top concept (for hierarchical vocabularies)                                   |
| `lang_set`    | `keyword[]` | Languages available for labels/description                                                    |
| `broader`     | `keyword[]` | identifiers of broader concepts                                                               |
| `narrower`    | `keyword[]` | identifiers of narrower concepts                                                              |
| `pref`        | `object`    | Preferred labels per language, e.g. `pref.fr`                                                 |
| `alt`         | `object`    | Alternative labels per language, e.g. `alt.en`                                                |
| `description` | `object`    | Descriptions per language (definitions, notes, or other), e.g. `description.en`               |
| `search_all`  | `text`      | Flattened text across all labels/descriptions, for free text search                           |

### Features

- **Folding analyzers** → case/diacritic insensitive, language-agnostic search.
- **Edge n-grams** (`.edge`) → fast autocomplete prefix search.
- **Raw keywords** (`.raw`) → exact match, normalized to lowercase/ascii.

---

### 3.2 Query examples

**Basic match query**  
Search in French preferred labels:

```bash
curl -s 'http://localhost:9200/concepts/_search' -H 'Content-Type: application/json' -d '{
  "size": 5,
  "query": { "match": { "pref.fr": "investissement" } }
}'

Autocomplete with edge n-grams
Prefix search on pref.fr.edge:

```bash
curl -s 'http://localhost:9200/concepts/_search' -H 'Content-Type: application/json' -d '{
  "size": 5,
  "query": { "match": { "pref.fr.edge": "inves" } }
}'
```

Cross-language free text search
Use the search_all field to match across all languages and labels:

```bash
curl -s 'http://localhost:9200/concepts/_search' -H 'Content-Type: application/json' -d '{
  "size": 5,
  "query": { "match": { "search_all": "growth" } }
}'
```

Exact IRI lookup

```bash
curl -s 'http://localhost:9200/concepts/_search' -H 'Content-Type: application/json' -d '{
  "query": { "term": { "iri": "http://zbw.eu/beta/external_identifiers/jel#O43" } }
}'
```

### 3.3 Usage

**Build a per-vocabulary image (at build time)**

```bash
# Example: build a JEL image
# 1. Convert RDF to NDJSON
mkdir -p build/jel
python3 loaders/load_skos.py   --in thesauri/jel/2024-01-01/jel.rdf   --out build/jel/concepts.ndjson.gz   --scheme JEL
# 2. Build Docker image with embedded data
docker build -f docker/Dockerfile \
  --build-arg CONCEPTS_SRC=build/jel/concepts.ndjson.gz \
  -t jel-os:2024-01 .
```

**Run**

```bash
# Start the container
docker run --rm -p 9200:9200 jel-os:2024-01
```

OpenSearch will start with the index `concepts_v1` and alias `concepts` ready to query.

**Test output**

```bash
# Search for "investissement" in all fields/languages
curl -s 'http://localhost:9200/concepts/_search' \
  -H 'Content-Type: application/json' \
  -d '{
    "size": 5,
    "query": {
      "multi_match": {
        "query": "investissement",
        "fields": ["pref.*", "alt.*", "description.*", "search_all"]
      }
    },
    "highlight": {
      "fields": {
        "pref.*": {},
        "alt.*": {},
        "description.*": {}
      }
    }
  }'                                  
```
## 4. Development

### 4.1 How to handle dependencies

To add a new dependency:

```bash
uv add --dev rdflib pylint
# or
uv add requests 
``` 

To export dependencies to requirements.txt files for production use:

```
# Only main dependencies (exclude dev group)
uv export --format requirements-txt \
  --no-annotate --no-hashes --no-header \
  --no-group dev \
  -o requirements.txt
```

To include dev dependencies:

```
# Main + dev (include dev group alongside main)
uv export --format requirements-txt \
  --no-annotate --no-hashes --no-header \
  --group dev \
  -o requirements-dev.txt
```