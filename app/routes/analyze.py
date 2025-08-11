from __future__ import annotations

import asyncio
import re
from typing import Optional, Dict, Any, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.article import Article
from app.models.highlight import Highlight
from app.routes.articles import ArticleOut

from app.services.llm import llm_score, llm_summary, extract_claims
from app.services.sourcing import find_primary_sources
from app.services.highlight_extractor import extract_highlights as local_extract_highlights

router = APIRouter(prefix="/analyze", tags=["analyze"])


class AnalyzeIn(BaseModel):
    title: Optional[str] = None
    outlet: Optional[str] = None
    url: Optional[str] = None
    text: Optional[str] = None

    @field_validator("text", mode="before")
    @classmethod
    def empty_to_none(cls, v):
        return v if v and str(v).strip() else None


def _strip_html(html: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _bias_band(v: int) -> str:
    if v < 30:
        return "low"
    if v < 50:
        return "medium"
    if v < 70:
        return "high"
    return "extremely_high"


def _bias_index_from_scores(scores: Dict[str, Any]) -> int:
    if not scores:
        return 0
    emo = float(scores.get("emotional_tone", 0))
    frame = float(scores.get("framing_choices", 0))
    fact_inv = 100.0 - float(scores.get("factual_grounding", 0))
    src_inv = 100.0 - float(scores.get("source_transparency", 0))
    ideo = float(scores.get("ideological_stance", 0))
    val = 0.25 * frame + 0.25 * fact_inv + 0.20 * src_inv + 0.15 * emo + 0.15 * ideo
    return int(max(0, min(100, round(val))))


@router.post("", response_model=ArticleOut, status_code=201)
async def analyze(
    payload: AnalyzeIn,
    db: AsyncSession = Depends(get_db),
    full: bool = Query(False, description="Include claims + primary sources (slower)"),
):
    if not payload.url and not payload.text:
        raise HTTPException(status_code=400, detail="Provide url or text")

    # 1) Acquire text
    article_text = payload.text
    if not article_text and payload.url:
        try:
            async with httpx.AsyncClient(
                timeout=20,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            ) as client:
                res = await client.get(payload.url, follow_redirects=True)
                res.raise_for_status()
                article_text = _strip_html(res.text)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {e}")

    if not article_text:
        raise HTTPException(status_code=400, detail="No text to analyze")

    # 2) LLM tasks
    async def _run_score():
        return await asyncio.to_thread(llm_score, article_text)

    async def _run_summary():
        return await asyncio.to_thread(llm_summary, article_text)

    tasks: List[asyncio.Future] = [
        asyncio.wait_for(_run_score(), timeout=25),
        asyncio.wait_for(_run_summary(), timeout=25),
    ]
    if full:
        async def _run_claims():
            return await asyncio.to_thread(extract_claims, article_text)
        tasks.append(asyncio.wait_for(_run_claims(), timeout=25))

    try:
        results = await asyncio.gather(*tasks)
        score_res = results[0]
        summary_text = results[1]
        claims: List[Dict[str, Any]] = results[2] if full and len(results) > 2 else []
    except asyncio.TimeoutError:
        # fallbacks (don’t fail the request)
        score_res = await asyncio.to_thread(llm_score, article_text)
        summary_text = await asyncio.to_thread(llm_summary, article_text)
        claims = []

    scores: Dict[str, Any] = score_res.get("scores", {}) or {}
    raw_highlights: List[Dict[str, Any]] = score_res.get("highlights", []) or []

    # 3) Normalize LLM highlights
    def _norm(h: Dict[str, Any]) -> Dict[str, Any]:
        t = (h.get("text") or h.get("data", {}).get("text") or "").strip()
        start = int(h.get("start", h.get("data", {}).get("start", 0)) or 0)
        end = int(h.get("end", h.get("data", {}).get("end", 0)) or 0)
        if end < start or end - start > 2000:
            start, end = 0, 0
        return {
            "dimension": h.get("dimension", "framing_choices"),
            "text": t,
            "start": start,
            "end": end,
            "reason": (h.get("reason") or h.get("data", {}).get("reason") or "").strip(),
            "confidence": float(h.get("confidence") or h.get("data", {}).get("confidence") or 0.6),
        }

    highlights: List[Dict[str, Any]] = []
    for h in raw_highlights:
        n = _norm(h)
        if n["text"] and "return only json" not in n["text"].lower():
            highlights.append(n)

    # 3b) Merge with local regex extractor (dedupe by (dimension, text))
    seen = {(h["dimension"], h["text"]) for h in highlights}
    try:
        for h in local_extract_highlights(article_text):
            dim = h.get("dimension", "framing_choices")
            dat = h.get("data", {}) or {}
            txt = dat.get("text", "")
            if not txt or (dim, txt) in seen:
                continue
            highlights.append({
                "dimension": dim,
                "text": txt,
                "start": int(dat.get("start", 0) or 0),
                "end": int(dat.get("end", 0) or 0),
                "reason": (dat.get("reason") or "").strip(),
                "confidence": float(dat.get("confidence", 0.75)),
            })
            seen.add((dim, txt))
    except Exception:
        pass

    # 3c) Last-resort fallback: synthesize highlights from the summary if none found
    if not highlights and summary_text:
        import re as _re
        sents = _re.split(r'(?<=[.!?])\s+', summary_text.strip())
        for i, s in enumerate([s for s in sents if len(s.split()) >= 8][:2]):
            highlights.append({
                "dimension": "framing_choices" if i == 0 else "emotional_tone",
                "text": s[:240],
                "start": 0,
                "end": 0,
                "reason": "Representative sentence extracted as fallback.",
                "confidence": 0.6,
            })

    # keep it tight
    highlights = highlights[:20]

    # 4) Enrich claims with sources (bounded)
    enriched_claims: List[Dict[str, Any]] = []
    if full and claims:
        for c in claims[:8]:
            q = (c.get("text") or "").strip()
            if not q:
                continue
            try:
                sources = await asyncio.wait_for(
                    asyncio.to_thread(find_primary_sources, q, 3),
                    timeout=5,
                )
            except asyncio.TimeoutError:
                sources = []
            enriched_claims.append({
                "text": q,
                "rationale": c.get("rationale"),
                "confidence": c.get("confidence"),
                "sources": (sources or [])[:2],
            })

    # 5) Overall score
    bias_index = _bias_index_from_scores(scores)
    overall = {"value": bias_index, "band": _bias_band(bias_index)}

    # 6) Persist Article
    row = Article(
        title=payload.title or (payload.url or "Untitled"),
        outlet=(payload.outlet or None),
        url=payload.url,
        scores=scores,
        highlights=highlights,        # optional copy on row
        summary=(summary_text or None),
        claims=enriched_claims,       # [] when not full
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # 7) Persist Highlights
    for h in highlights:
        db.add(
            Highlight(
                article_id=row.id,
                dimension=h["dimension"],
                data={
                    "text": h["text"],
                    "start": h["start"],
                    "end": h["end"],
                    "reason": h["reason"],
                    "confidence": h["confidence"],
                },
            )
        )
    await db.commit()

    # 8) Respond
    payload_out: Dict[str, Any] = {
        "id": row.id,
        "title": row.title,
        "outlet": row.outlet,
        "url": row.url,
        "published_at": getattr(row, "published_at", None),
        "summary": row.summary,
        "scores": row.scores,
        "overall": overall,
        "claims": row.claims or [],
    }
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=payload_out)