"""
Fetch recent papers from PubMed, arXiv, bioRxiv and medRxiv.

Each fetch_* function returns a list of dicts with a common schema:
    {
        "id": str,            # stable unique id, e.g. "pubmed:39012345"
        "source": str,        # "pubmed" | "arxiv" | "biorxiv" | "medrxiv"
        "title": str,
        "abstract": str,
        "authors": list[str],
        "date": str,          # ISO date
        "url": str,
        "doi": str | None,
        "journal": str,        # journal name; only populated for pubmed, "" otherwise
    }
"""
import time
import datetime as dt
import xml.etree.ElementTree as ET

import requests
import feedparser

UA = {"User-Agent": "paper-radar/1.0 (personal research feed; contact: you@example.com)"}


def _get_with_retries(url, *, params=None, timeout=30, retries=3, backoff=5):
    """GET with a few retries on network/timeout errors, since bioRxiv/medRxiv/PubMed
    APIs are occasionally slow or flaky. Raises the last exception if all attempts fail."""
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return requests.get(url, params=params, headers=UA, timeout=timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_exc = exc
            if attempt < retries:
                print(f"  ...request to {url} failed ({exc.__class__.__name__}), "
                      f"retry {attempt}/{retries - 1} in {backoff}s")
                time.sleep(backoff)
    raise last_exc


def _today_and_lookback(days_back: int):
    end = dt.date.today()
    start = end - dt.timedelta(days=days_back)
    return start, end


# ---------------------------------------------------------------- PubMed ---

def fetch_pubmed(keywords, max_results, email, api_key="", days_back=4):
    # Use EDAT (date the record was added/updated in PubMed) rather than the journal's
    # print "Date - Publication", which is often set weeks/months away from when the
    # paper actually appeared and silently zeroes out a tight recency window.
    start, end = _today_and_lookback(days_back)
    # Exact-phrase match per keyword — "molecular epidemiology" must appear as that
    # literal phrase in title/abstract, not just as co-occurring words anywhere. This
    # matches how bioRxiv/medRxiv already filter (substring match) so all four sources
    # now apply the same strictness.
    def kw_clause(k):
        return f'"{k}"[Title/Abstract]'
    query = "(" + " OR ".join(kw_clause(k) for k in keywords) + ")"

    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "datetype": "edat",
        "mindate": f"{start:%Y/%m/%d}",
        "maxdate": f"{end:%Y/%m/%d}",
        "email": email,
        "tool": "paper-radar",
    }
    if api_key:
        params["api_key"] = api_key

    r = _get_with_retries(f"{base}/esearch.fcgi", params=params, timeout=30)
    r.raise_for_status()
    ids = r.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []

    time.sleep(0.34)  # stay under rate limit
    fetch_params = {
        "db": "pubmed",
        "id": ",".join(ids),
        "retmode": "xml",
        "email": email,
        "tool": "paper-radar",
    }
    if api_key:
        fetch_params["api_key"] = api_key
    r = _get_with_retries(f"{base}/efetch.fcgi", params=fetch_params, timeout=30)
    r.raise_for_status()

    root = ET.fromstring(r.content)
    papers = []
    for art in root.findall(".//PubmedArticle"):
        pmid = art.findtext(".//PMID", default="")
        title = " ".join((art.findtext(".//ArticleTitle") or "").split())
        abstract_parts = [
            "".join(node.itertext()) for node in art.findall(".//Abstract/AbstractText")
        ]
        abstract = " ".join(" ".join(p.split()) for p in abstract_parts)
        authors = []
        for a in art.findall(".//AuthorList/Author"):
            last = a.findtext("LastName")
            fore = a.findtext("ForeName")
            if last:
                authors.append(f"{fore} {last}".strip() if fore else last)
        doi = None
        for eid in art.findall(".//ArticleIdList/ArticleId"):
            if eid.get("IdType") == "doi":
                doi = eid.text
        year = art.findtext(".//PubDate/Year") or ""
        month = art.findtext(".//PubDate/Month") or "01"
        day = art.findtext(".//PubDate/Day") or "01"
        date = f"{year}-{month}-{day}" if year else ""
        journal = art.findtext(".//Journal/Title") or art.findtext(".//Journal/ISOAbbreviation") or ""

        if not title or not abstract:
            continue
        papers.append({
            "id": f"pubmed:{pmid}",
            "source": "pubmed",
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "date": date,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "doi": doi,
            "journal": journal,
        })
    return papers


# ----------------------------------------------------------------- arXiv ---

def fetch_arxiv(keywords, categories, max_results, days_back=4):
    # Exact-phrase match per keyword, consistent with PubMed/bioRxiv/medRxiv.
    def kw_clause(k):
        return f'abs:"{k}"'

    kw_query = " OR ".join(kw_clause(k) for k in keywords)
    cat_query = " OR ".join(f"cat:{c}" for c in categories) if categories else ""
    search_query = f"({kw_query})" + (f" AND ({cat_query})" if cat_query else "")

    params = {
        "search_query": search_query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max(max_results, 100),  # fetch a wider pool before date-filtering locally
    }
    r = _get_with_retries("http://export.arxiv.org/api/query", params=params, timeout=30)
    r.raise_for_status()
    feed = feedparser.parse(r.content)

    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days_back)
    papers = []
    for entry in feed.entries:
        published = dt.datetime(*entry.published_parsed[:6])
        if published < cutoff:
            continue
        arxiv_id = entry.id.rsplit("/abs/", 1)[-1]
        papers.append({
            "id": f"arxiv:{arxiv_id}",
            "source": "arxiv",
            "title": " ".join(entry.title.split()),
            "abstract": " ".join(entry.summary.split()),
            "authors": [a.name for a in getattr(entry, "authors", [])],
            "date": published.date().isoformat(),
            "url": entry.link,
            "doi": getattr(entry, "arxiv_doi", None),
        })
    return papers


# ------------------------------------------------------- bioRxiv/medRxiv ---

def _fetch_rxiv(server, keywords, max_results, days_back=4):
    """bioRxiv/medRxiv only support browsing by date, not keyword search server-side,
    so we pull the recent window and filter locally against title+abstract."""
    start, end = _today_and_lookback(days_back)
    papers = []
    cursor = 0
    keywords_lower = [k.lower() for k in keywords]
    while True:
        url = f"https://api.biorxiv.org/details/{server}/{start:%Y-%m-%d}/{end:%Y-%m-%d}/{cursor}"
        try:
            r = _get_with_retries(url, timeout=30)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            print(f"  {server}: giving up on page at cursor={cursor} after retries ({exc.__class__.__name__}); "
                  f"returning {len(papers)} papers fetched so far")
            break
        if r.status_code != 200:
            break
        data = r.json()
        collection = data.get("collection", [])
        if not collection:
            break
        for item in collection:
            title = item.get("title", "")
            abstract = item.get("abstract", "")
            haystack = f"{title} {abstract}".lower()
            if any(k in haystack for k in keywords_lower):
                doi = item.get("doi")
                papers.append({
                    "id": f"{server}:{doi}",
                    "source": server,
                    "title": " ".join(title.split()),
                    "abstract": " ".join(abstract.split()),
                    "authors": [a.strip() for a in item.get("authors", "").split(";") if a.strip()],
                    "date": item.get("date", ""),
                    "url": f"https://doi.org/{doi}" if doi else "",
                    "doi": doi,
                })
        if len(papers) >= max_results or len(collection) < 100:
            break
        cursor += 100
        time.sleep(0.2)
    return papers[:max_results]


def fetch_biorxiv(keywords, max_results, days_back=4):
    return _fetch_rxiv("biorxiv", keywords, max_results, days_back)


def fetch_medrxiv(keywords, max_results, days_back=4):
    return _fetch_rxiv("medrxiv", keywords, max_results, days_back)
