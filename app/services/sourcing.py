from __future__ import annotations

from typing import List, Dict, Any
from urllib.parse import urlparse

from app.utils.config import TAVILY_API_KEY


def _bonus(url: str, title: str = "") -> float:
    """Heuristic bump for likely primary sources."""
    u = (url or "").lower()
    t = (title or "").lower()
    host = urlparse(u).netloc

    b = 0.0
    if host.endswith(".gov") or host.endswith(".mil") or host.endswith(".edu"):
        b += 0.25
    if u.endswith(".pdf") or "filetype:pdf" in u:
        b += 0.15
    if "press" in t and "release" in t:
        b += 0.1
    if "official" in t or "statement" in t:
        b += 0.08
    # penalize obvious aggregators a touch
    for bad in ("wikipedia.org", "reddit.com", "x.com", "twitter.com", "facebook.com", "medium.com"):
        if host.endswith(bad):
            b -= 0.25
            break
    return b


def _unique_by_domain(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for it in items:
        host = urlparse((it.get("url") or "").lower()).netloc
        if not host or host in seen:
            continue
        seen.add(host)
        out.append(it)
    return out


def find_primary_sources(query: str, k: int = 3) -> List[Dict[str, Any]]:
    """
    Return up to k likely-primary sources for a claim.
    Each item: { title, url, score, published }
    Returns [] if Tavily is not configured or any error occurs.
    """
    if not TAVILY_API_KEY:
        return []

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=TAVILY_API_KEY)

        # Bias the search itself toward official docs and records.
        biased_query = (
            f"{query} "
            'site:.gov OR site:.mil OR site:.edu OR "press release" OR "official statement" '
            'OR filetype:pdf'
        )

        # Pull a few extra so we can re-rank/dedupe.
        raw = client.search(
            query=biased_query,
            search_depth="advanced",
            max_results=min(max(k * 3, 5), 12),
            include_answer=False,
        )

        items: List[Dict[str, Any]] = []
        for r in raw.get("results", []):
            url = r.get("url") or ""
            title = r.get("title") or url
            base = float(r.get("score") or 0.0)
            bonus = _bonus(url, title)
            items.append(
                {
                    "title": title,
                    "url": url,
                    "score": max(0.0, min(1.0, base + bonus)),
                    "published": r.get("published_date"),
                }
            )

        # Re-rank with our bonus, prefer unique domains, then trim.
        items.sort(key=lambda x: x["score"], reverse=True)
        items = _unique_by_domain(items)
        return items[: max(1, k)]

    except Exception:
        # fail-safe: no sources rather than breaking analysis
        return []