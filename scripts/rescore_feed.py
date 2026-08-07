"""Re-scores data/feed.json against the current preference vector and re-sorts it.
Run after update_preferences.py so the feed re-ranks immediately when you rate something,
rather than waiting for tomorrow's fetch."""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load_json(path, default):
    p = Path(path)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return default


def main():
    pref_vec = load_json(DATA / "preference_vector.json", None)
    if pref_vec is None:
        print("No preference vector yet — skipping rescore.")
        return
    pref_vec = np.array(pref_vec)

    feed = load_json(DATA / "feed.json", [])
    embeddings = load_json(DATA / "embeddings.json", {})

    for p in feed:
        emb = embeddings.get(p["id"])
        if emb is not None:
            p["score"] = round(float(np.array(emb) @ pref_vec), 4)

    feed.sort(key=lambda p: p["score"], reverse=True)
    with open(DATA / "feed.json", "w") as f:
        json.dump(feed, f, indent=2, ensure_ascii=False)

    print(f"Re-scored {len(feed)} papers in feed.")


if __name__ == "__main__":
    main()
