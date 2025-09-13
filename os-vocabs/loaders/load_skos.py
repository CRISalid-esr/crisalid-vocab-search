# loaders/load_skos.py
import argparse
import gzip
import json
import os
import re
from typing import Dict, List

from rdflib import Graph, Namespace, URIRef, RDF, Literal

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

_ws_re = re.compile(r"\s+")


def _norm_text(s: str) -> str:
    # Collapse whitespace and trim
    return _ws_re.sub(" ", s).strip()


def _collect_lang_literals(
        graph: Graph, subject: URIRef, predicate: URIRef
) -> Dict[str, List[str]]:
    """
    Collect rdflib Literals under (subject, predicate) into
    a dict lang -> [texts], preserving order and de-duplicating per lang.
    """
    out: Dict[str, List[str]] = {}
    seen_per_lang: Dict[str, set] = {}

    for lit in graph.objects(subject, predicate):
        if not isinstance(lit, Literal):
            continue
        lang = (lit.language or "und").lower()
        txt = _norm_text(str(lit))
        if not txt:
            continue
        if lang not in out:
            out[lang] = []
            seen_per_lang[lang] = set()
        if txt not in seen_per_lang[lang]:
            out[lang].append(txt)
            seen_per_lang[lang].add(txt)

    return out


def _unique_flatten(*iterables) -> List[str]:
    """
    Flatten multiple iterables into a single list with order-preserving
    de-duplication.
    """
    seen = set()
    res: List[str] = []
    for it in iterables:
        for x in it:
            if not x:
                continue
            if x not in seen:
                res.append(x)
                seen.add(x)
    return res


def concept_to_doc(graph: Graph, concept_uri: URIRef,  # pylint: disable=too-many-locals
                   scheme: str | None = None) -> dict:
    """Extract one SKOS concept into the normalized JSON model (final mapping)."""

    # Labels / descriptions by lang
    pref = _collect_lang_literals(graph, concept_uri, SKOS.prefLabel)
    alt = _collect_lang_literals(graph, concept_uri, SKOS.altLabel)

    # Use SKOS definition + note as "description"
    description = {}
    # Merge definitions
    defs = _collect_lang_literals(graph, concept_uri, SKOS.definition)
    for lang, vals in defs.items():
        description.setdefault(lang, [])
        description[lang].extend(vals)
    # Merge notes
    notes = _collect_lang_literals(graph, concept_uri, SKOS.note)
    for lang, vals in notes.items():
        description.setdefault(lang, [])
        # de-duplicate while preserving order per lang
        existing = set(description[lang])
        for v in vals:
            if v not in existing:
                description[lang].append(v)
                existing.add(v)

    # Lang set across fields
    lang_set = sorted(set(pref.keys()) | set(alt.keys()) | set(description.keys()))

    # Hierarchy
    broader = [str(o) for o in graph.objects(concept_uri, SKOS.broader)]
    narrower = [str(o) for o in graph.objects(concept_uri, SKOS.narrower)]

    # search_all: concatenate all textual bits across languages
    all_texts: List[str] = []
    for d in (pref, alt, description):
        for vals in d.values():
            all_texts.extend(vals)
    search_all = " ".join(_unique_flatten(all_texts))

    doc = {
        "iri": str(concept_uri),
        "scheme": scheme or "",
        "top_concept": bool(list(graph.objects(concept_uri, SKOS.topConceptOf))),
        "lang_set": lang_set,
        "broader": broader,
        "narrower": narrower,
        "pref": pref,
        "alt": alt,
        "description": description,
        "search_all": search_all,
    }
    return doc


def main():
    """Command-line interface: convert SKOS file to normalized NDJSON.gz."""
    ap = argparse.ArgumentParser(description="SKOS → normalized NDJSON.gz for OpenSearch")
    ap.add_argument("--in", dest="infile", required=True, help="Input SKOS file (.rdf/.ttl/...)")
    ap.add_argument("--out", dest="outfile", required=True, help="Output NDJSON.gz")
    ap.add_argument("--scheme", dest="scheme", default=None, help="Optional scheme ID to attach")
    args = ap.parse_args()

    g = Graph()
    # rdflib will auto-detect format from extension/content when possible
    g.parse(args.infile)

    out_dir = os.path.dirname(args.outfile)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    count = 0
    with gzip.open(args.outfile, "wt", encoding="utf-8") as out:
        for s in g.subjects(RDF.type, SKOS.Concept):
            doc = concept_to_doc(g, s, args.scheme)
            out.write(json.dumps(doc, ensure_ascii=False) + "\n")
            count += 1

    print(f"Wrote {count} concepts → {args.outfile}")


if __name__ == "__main__":
    main()
