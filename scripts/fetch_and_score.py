"""
Daily entry point, run by .github/workflows/daily.yml

1. Load config.yaml
2. Fetch recent papers from each enabled source, filtered by keyword
3. Drop anything already seen (data/seen_ids.json)
4. Embed title+abstract
5. Score against data/preference_vector.json (cosine similarity); if no vector yet, score=0.5 for all
6. Write data/papers/YYYY-MM-DD.json (today's batch) and refresh data/feed.json (rolling window,
   sorted by score desc, capped at feed_size)
7. Persist embeddings for rated/feed papers to data/embeddings.json (used by update_preferences.py)
8. Update data/seen_ids.json
"""
import json
import datetime as dt
from pathlib import Path

import yaml
import numpy as np

import sources
from embed import embed_texts, paper_text, cosine_sim

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
(DATA / "papers").mkdir(exist_ok=True)


def load_json(path, default):
    p = Path(path)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return default


def save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def main():
    config = yaml.safe_load(open(ROOT / "config.yaml"))
    keywords = config["keywords"]
    sources_enabled = config.get("sources", ["pubmed", "arxiv", "biorxiv", "medrxiv"])
    max_per_source = config.get("max_per_source_per_day", 60)
    feed_size = config.get("feed_size", 200)

    seen_ids = set(load_json(DATA / "seen_ids.json", []))

    fetched = []
    if "pubmed" in sources_enabled:
        fetched += sources.fetch_pubmed(
            keywords, max_per_source,
            email=config.get("pubmed_email", ""),
            api_key=config.get("pubmed_api_key", ""),
        )
    if "arxiv" in sources_enabled:
        fetched += sources.fetch_arxiv(keywords, config.get("arxiv_categories", []), max_per_source)
    if "biorxiv" in sources_enabled:
        fetched += sources.fetch_biorxiv(keywords, max_per_source)
    if "medrxiv" in sources_enabled:
        fetched += sources.fetch_medrxiv(keywords, max_per_source)

    new_papers = [p for p in fetched if p["id"] not in seen_ids]
    # dedupe within this batch too (same paper can appear via multiple keyword hits)
    dedup = {}
    for p in new_papers:
        dedup[p["id"]] = p
    new_papers = list(dedup.values())

    print(f"Fetched {len(fetched)} total, {len(new_papers)} new after dedup.")

    if not new_papers:
        return

    texts = [paper_text(p) for p in new_papers]
    embeddings = embed_texts(texts)

    pref_vec = load_json(DATA / "preference_vector.json", None)
    if pref_vec is not None:
        pref_vec = np.array(pref_vec)
        scores = cosine_sim(pref_vec, embeddings)
    else:
        scores = np.full(len(new_papers), 0.5)  # neutral until preferences exist

    embeddings_store = load_json(DATA / "embeddings.json", {})
    for p, emb, score in zip(new_papers, embeddings, scores):
        p["score"] = round(float(score), 4)
        p["fetched_at"] = dt.date.today().isoformat()
        embeddings_store[p["id"]] = emb.tolist()

    today_str = dt.date.today().isoformat()
    save_json(DATA / "papers" / f"{today_str}.json", new_papers)

    feed = load_json(DATA / "feed.json", [])
    feed_ids = {p["id"] for p in feed}
    feed += [p for p in new_papers if p["id"] not in feed_ids]
    feed.sort(key=lambda p: p["score"], reverse=True)
    feed = feed[:feed_size]
    save_json(DATA / "feed.json", feed)

    # keep embeddings only for papers still referenced (feed + all-time ratings) to bound file size
    ratings = load_json(DATA / "ratings.json", [])
    keep_ids = {p["id"] for p in feed} | {r["id"] for r in ratings}
    embeddings_store = {k: v for k, v in embeddings_store.items() if k in keep_ids}
    save_json(DATA / "embeddings.json", embeddings_store)

    seen_ids |= {p["id"] for p in new_papers}
    save_json(DATA / "seen_ids.json", sorted(seen_ids))

    print(f"Feed now has {len(feed)} papers. Top score: {feed[0]['score'] if feed else 'n/a'}")


if __name__ == "__main__":
    main()
