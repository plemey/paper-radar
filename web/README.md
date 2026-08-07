# Paper Radar

A personal daily paper-discovery app: fetches new papers from **PubMed, arXiv, bioRxiv and medRxiv**,
scores them against a preference vector learned from your ratings (and optionally seeded from a
`.bib` file), and shows you a swipeable feed as an installable web app (PWA) that works on
Mac, iPhone and iPad.

Everything runs on GitHub's free tier: GitHub Actions does the daily fetching/scoring/embedding,
and GitHub Pages hosts the front end. There is no server to maintain.

## How it works

```
[GitHub Action, daily cron]
   fetch_and_score.py
     -> query PubMed / arXiv / bioRxiv / medRxiv using config.yaml keywords
     -> dedupe against data/seen_ids.json
     -> embed title+abstract (sentence-transformers, all-MiniLM-L6-v2)
     -> score = cosine similarity to data/preference_vector.json
     -> write data/papers/YYYY-MM-DD.json + refresh data/feed.json (rolling 200 latest)
     -> commit results back to the repo

[GitHub Pages, static site in /web]
   index.html / app.js
     -> reads data/feed.json (via raw.githubusercontent.com, always fresh)
     -> renders cards sorted by score, with 👍 / 👎 / skip
     -> on rating, calls the GitHub Contents API directly from the browser
        (using a fine-grained Personal Access Token you paste into Settings once)
        to append to data/ratings.json and commit it

[GitHub Action, triggered on push to data/ratings.json or data/seed_vector.json]
   update_preferences.py
     -> recomputes preference vector = weighted centroid of liked embeddings
        minus disliked embeddings (+ optional .bib seed vector)
     -> writes data/preference_vector.json
```

Ratings and the preference vector are just JSON files versioned in the repo — no database.
Everything syncs automatically across your devices because they all just read/write the same
GitHub repo.

## One-time setup

1. **Create a new GitHub repo** (private is fine), and push the contents of this folder to it.

2. **Enable GitHub Pages**: repo Settings → Pages → Deploy from branch → `main` → `/web` (or `/docs`,
   see note below) folder.

3. **Create a fine-grained Personal Access Token** (Settings → Developer settings → Personal access
   tokens → Fine-grained tokens):
   - Repository access: only this repo
   - Permissions: **Contents: Read and write**
   - Copy the token — you'll paste it once into the app's Settings screen (it's stored only in
     your browser's local storage, never sent anywhere but GitHub's API).

4. **Edit `config.yaml`** with your keywords/topics (see below). Commit and push.

5. **Seed with your `.bib` file** (optional but recommended): open the app → Settings → Import
   `.bib`. This uploads the file to `data/seed.bib` in the repo, which triggers a workflow that
   looks up abstracts (via CrossRef/PubMed) for each entry, embeds them, and folds them into your
   preference vector as a warm start — so you're not starting from a blank slate.

6. Wait for the first daily run (or trigger it manually: Actions tab → "Daily fetch" → Run workflow),
   then open the GitHub Pages URL on your Mac/iPad/iPhone and add it to your home screen (Safari
   → Share → Add to Home Screen) for a native-app-like icon and full-screen experience.

## `config.yaml`

```yaml
keywords:
  - "phylodynamics"
  - "viral phylogeography"
  - "Bayesian phylogenetics"
  - "protein structure evolution"
  - "ancient DNA virus"
sources: [pubmed, arxiv, biorxiv, medrxiv]
arxiv_categories: [q-bio.PE, q-bio.GN]   # optional, narrows arXiv/bioRxiv-style category filtering
max_per_source_per_day: 60
feed_size: 200
```

Add/remove keywords any time — they take effect on the next daily run. Keywords are OR'd together
for retrieval; the *ranking* you see is driven by the learned preference vector, not the keywords,
so keywords can stay broad.

## Costs / limits

- GitHub Actions free tier: 2,000 minutes/month (private repos) — a daily run takes ~2-4 minutes,
  so you'll use a small fraction of that.
- GitHub Pages: free, unlimited for personal use.
- No paid APIs are used — PubMed E-utilities, arXiv API, and the bioRxiv/medRxiv API are all free;
  embeddings run locally in the Action using an open model (no OpenAI key needed).

## Files

- `.github/workflows/daily.yml` — daily cron (fetch + score + commit)
- `.github/workflows/update_preferences.yml` — runs on push to `data/ratings.json` or `data/seed.bib`
- `scripts/sources.py` — API clients for PubMed / arXiv / bioRxiv / medRxiv
- `scripts/embed.py` — embedding helper (sentence-transformers)
- `scripts/fetch_and_score.py` — daily entry point
- `scripts/update_preferences.py` — recomputes preference vector from ratings + bib seed
- `scripts/import_bib.py` — parses `data/seed.bib`, resolves abstracts, builds seed vector
- `web/` — the PWA (plain HTML/JS, no build step)
- `config.yaml` — your keyword/topic config
- `data/` — all persisted state (papers, ratings, preference vector)
