"""
Run whenever data/ratings.json or data/seed_vector.json changes.

Preference vector = blend of:
  - "learned" direction: mean(liked embeddings) - 0.5 * mean(disliked embeddings)
  - "seed" direction: centroid of embeddings from your imported .bib file (data/seed_vector.json,
    produced by import_bib.py)

The seed's influence decays as you accumulate ratings, so the app leans on your existing
library at first (cold start) and increasingly on your actual click behavior over time.
"""
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


def normalize(v):
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def main():
    ratings = load_json(DATA / "ratings.json", [])
    embeddings = load_json(DATA / "embeddings.json", {})
    seed_vec = load_json(DATA / "seed_vector.json", None)

    liked = [np.array(embeddings[r["id"]]) for r in ratings
              if r["rating"] > 0 and r["id"] in embeddings]
    disliked = [np.array(embeddings[r["id"]]) for r in ratings
                 if r["rating"] < 0 and r["id"] in embeddings]

    learned = None
    if liked:
        learned = np.mean(liked, axis=0)
        if disliked:
            learned = learned - 0.5 * np.mean(disliked, axis=0)
        learned = normalize(learned)

    if learned is None and seed_vec is None:
        print("No ratings and no seed vector yet — nothing to compute.")
        return

    if learned is None:
        final = np.array(seed_vec)
    elif seed_vec is None:
        final = learned
    else:
        n_ratings = len(ratings)
        seed_weight = max(0.1, 1.0 / (1.0 + n_ratings / 10.0))
        final = normalize(seed_weight * np.array(seed_vec) + (1 - seed_weight) * learned)

    final = normalize(final)
    with open(DATA / "preference_vector.json", "w") as f:
        json.dump(final.tolist(), f)

    print(f"Preference vector updated from {len(liked)} liked / {len(disliked)} disliked ratings"
          + (" + bib seed." if seed_vec is not None else "."))


if __name__ == "__main__":
    main()
