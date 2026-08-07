"""
Run whenever data/seed.bib changes (uploaded via the web app's Settings screen).

For each entry in the .bib file:
  1. Use the abstract field if the .bib already has one (common if exported from Zotero/EndNote).
  2. Otherwise try CrossRef (by DOI if present, else by title match) for an abstract.
  3. Otherwise try PubMed (esearch by title) for an abstract.
  4. If nothing found, fall back to just the title.

Embeds all resolved title+abstract texts and writes their centroid to data/seed_vector.json,
which update_preferences.py blends in as a cold-start prior.
"""
import json
import re
import time
from pathlib import Path

import requests
import bibtexparser
import numpy as np

from embed import embed_texts

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = {"User-Agent": "paper-radar/1.0 (personal research feed)"}


def crossref_abstract(doi=None, title=None):
    try:
        if doi:
            r = requests.get(f"https://api.crossref.org/works/{doi}", headers=UA, timeout=15)
            if r.status_code == 200:
                abs_ = r.json().get("message", {}).get("abstract", "")
                if abs_:
                    return re.sub("<[^<]+?>", "", abs_)
        if title:
            r = requests.get("https://api.crossref.org/works",
                              params={"query.bibliographic": title, "rows": 1}, headers=UA, timeout=15)
            if r.status_code == 200:
                items = r.json().get("message", {}).get("items", [])
                if items:
                    abs_ = items[0].get("abstract", "")
                    if abs_:
                        return re.sub("<[^<]+?>", "", abs_)
    except requests.RequestException:
        pass
    return None


def pubmed_abstract(title):
    try:
        r = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                          params={"db": "pubmed", "term": f'"{title}"[Title]', "retmode": "json", "retmax": 1},
                          headers=UA, timeout=15)
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return None
        r = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                          params={"db": "pubmed", "id": ids[0], "retmode": "text", "rettype": "abstract"},
                          headers=UA, timeout=15)
        return r.text.strip() or None
    except requests.RequestException:
        return None


def main():
    bib_path = DATA / "seed.bib"
    if not bib_path.exists():
        print("No data/seed.bib found — skipping.")
        return

    with open(bib_path) as f:
        bib_db = bibtexparser.load(f)

    texts = []
    resolved = []
    for entry in bib_db.entries:
        title = entry.get("title", "").strip("{}")
        if not title:
            continue
        abstract = entry.get("abstract", "")
        doi = entry.get("doi")
        if not abstract:
            abstract = crossref_abstract(doi=doi, title=title) or ""
            time.sleep(0.2)
        if not abstract:
            abstract = pubmed_abstract(title) or ""
            time.sleep(0.34)
        texts.append(f"{title}. {abstract}")
        resolved.append({"title": title, "has_abstract": bool(abstract)})

    if not texts:
        print("No usable entries found in seed.bib.")
        return

    embeddings = embed_texts(texts)
    centroid = np.mean(embeddings, axis=0)
    centroid = centroid / np.linalg.norm(centroid)

    with open(DATA / "seed_vector.json", "w") as f:
        json.dump(centroid.tolist(), f)

    n_with_abs = sum(r["has_abstract"] for r in resolved)
    print(f"Seeded from {len(texts)} bib entries ({n_with_abs} with a resolved abstract, "
          f"{len(texts) - n_with_abs} title-only).")


if __name__ == "__main__":
    main()
