"""
Regenerates data/bibliography.bib from data/ratings.json.

Every paper with the most recent rating > 0 gets a BibTeX entry. Full metadata
(title/authors/doi/journal) is looked up from the daily data/papers/YYYY-MM-DD.json
archives, since those are never pruned (unlike feed.json / embeddings.json).

Run by .github/workflows/bibliography.yml whenever data/ratings.json changes
(i.e. right after you rate something in the app).
"""
import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

STOPWORDS = {"a", "an", "the", "of", "on", "in", "for", "and", "to", "with"}
SOURCE_LABEL = {
    "arxiv": "arXiv preprint",
    "biorxiv": "bioRxiv preprint",
    "medrxiv": "medRxiv preprint",
}


def load_json(path, default):
    p = Path(path)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return default


def build_paper_index():
    """id -> paper metadata, scanned from every daily archive file."""
    index = {}
    for path in sorted(glob.glob(str(DATA / "papers" / "*.json"))):
        for p in load_json(path, []):
            index[p["id"]] = p
    return index


def bibtex_escape(s):
    if not s:
        return ""
    return (
        s.replace("\\", r"\\")
         .replace("&", r"\&")
         .replace("%", r"\%")
         .replace("#", r"\#")
         .replace("_", r"\_")
    )


def make_key(paper, used_keys):
    last = ""
    if paper.get("authors"):
        parts = paper["authors"][0].split()
        last = parts[-1] if parts else ""
    last = re.sub(r"[^A-Za-z]", "", last) or "Anon"
    year = (paper.get("date") or "")[:4] or "nd"
    first_word = ""
    for w in re.findall(r"[A-Za-z]+", paper.get("title", "")):
        if w.lower() not in STOPWORDS:
            first_word = w.lower()
            break
    base = f"{last}{year}{first_word}"
    key = base
    i = 1
    while key in used_keys:
        i += 1
        key = f"{base}{chr(96 + i)}"  # a, b, c, ...
    used_keys.add(key)
    return key


def to_bibtex(paper, key):
    authors = " and ".join(bibtex_escape(a) for a in paper.get("authors", [])) or "Unknown"
    title = bibtex_escape(paper.get("title", ""))
    year = (paper.get("date") or "")[:4]
    journal = paper.get("journal") or SOURCE_LABEL.get(paper.get("source", ""), paper.get("source", ""))
    entry_type = "article" if paper.get("source") == "pubmed" and journal else "misc"

    lines = [f"@{entry_type}{{{key},"]
    lines.append(f"  title        = {{{{{title}}}}},")
    lines.append(f"  author       = {{{authors}}},")
    if year:
        lines.append(f"  year         = {{{year}}},")
    if entry_type == "article":
        lines.append(f"  journal      = {{{bibtex_escape(journal)}}},")
    else:
        lines.append(f"  howpublished = {{{bibtex_escape(journal)}}},")
    if paper.get("doi"):
        lines.append(f"  doi          = {{{paper['doi']}}},")
    if paper.get("url"):
        lines.append(f"  url          = {{{paper['url']}}},")
    lines.append("}")
    return "\n".join(lines)


def main():
    ratings = load_json(DATA / "ratings.json", [])

    # Most recent rating per paper id wins, so down-rating something later removes
    # it from the bibliography on the next rebuild.
    latest = {}
    for r in ratings:
        latest[r["id"]] = r
    positive_ids = [pid for pid, r in latest.items() if r.get("rating", 0) > 0]

    if not positive_ids:
        (DATA / "bibliography.bib").write_text("% No positively-rated papers yet.\n")
        print("No positively rated papers; wrote empty bibliography.")
        return

    index = build_paper_index()
    missing = [pid for pid in positive_ids if pid not in index]
    if missing:
        print(f"Warning: {len(missing)} positively-rated id(s) not found in data/papers/*.json "
              f"archives, skipping: {missing}")

    papers = [index[pid] for pid in positive_ids if pid in index]
    papers.sort(key=lambda p: p.get("date", ""), reverse=True)

    used_keys = set()
    entries = [to_bibtex(p, make_key(p, used_keys)) for p in papers]

    header = (
        "% Bibliography of positively-rated papers from paper-radar\n"
        "% Auto-generated — do not edit by hand, changes will be overwritten.\n"
        f"% {len(entries)} entries\n\n"
    )
    (DATA / "bibliography.bib").write_text(header + "\n\n".join(entries) + "\n")
    print(f"Wrote {len(entries)} entries to data/bibliography.bib")


if __name__ == "__main__":
    main()
