from __future__ import annotations

from io import StringIO
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.article import Article
from app.models.highlight import Highlight

router = APIRouter(prefix="/articles", tags=["articles"])


# ---------- Schemas ----------
class ScoresOut(BaseModel):
    emotional_tone: Optional[int] = 0
    framing_choices: Optional[int] = 0
    factual_grounding: Optional[int] = 0
    ideological_stance: Optional[int] = 0
    source_transparency: Optional[int] = 0


class ArticleOut(BaseModel):
    id: int
    title: str
    outlet: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[str] = None
    summary: Optional[str] = None
    scores: Dict[str, Any] = {}
    overall: Optional[Dict[str, Any]] = None
    claims: Optional[List[Dict[str, Any]]] = None

    class Config:
        from_attributes = True


# ---------- Routes ----------
@router.get("", response_model=List[ArticleOut])
async def list_articles(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Article).order_by(desc(Article.id)).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@router.get("/{article_id}", response_model=ArticleOut)
async def get_article(article_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(Article, article_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_article(article_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(delete(Article).where(Article.id == article_id))
    if res.rowcount == 0:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{article_id}/export.csv")
async def export_csv(article_id: int, db: AsyncSession = Depends(get_db)):
    """
    Export one CSV that mirrors the modal:
      - Meta
      - Summary
      - Scores (row per key)
      - Claims (row per claim with sources)
      - Highlights table
    """
    art = await db.get(Article, article_id)
    if not art:
        raise HTTPException(status_code=404, detail="Not found")

    # Highlights
    stmt = select(Highlight).where(Highlight.article_id == article_id).order_by(Highlight.id.asc())
    highlights = (await db.execute(stmt)).scalars().all()

    def esc(s: Any) -> str:
        t = "" if s is None else str(s)
        t = t.replace('"', '""')
        if any(c in t for c in [",", "\n", '"']):
            return f'"{t}"'
        return t

    buf = StringIO()

    # Meta
    buf.write("section,key,value\n")
    meta = {
        "id": art.id,
        "title": art.title,
        "outlet": art.outlet,
        "url": art.url,
        "published_at": art.published_at,
        "created_at": getattr(art, "created_at", None),
    }
    for k, v in meta.items():
        buf.write(",".join(["meta", esc(k), esc(v)]) + "\n")

    # Summary
    buf.write(",".join(["summary", "text", esc(art.summary or "")]) + "\n")

    # Scores
    scores = art.scores or {}
    for k, v in scores.items():
        buf.write(",".join(["scores", esc(k), esc(v)]) + "\n")

    buf.write("\n")

    # Claims (one row per claim)
    # columns: claims,text,rationale,confidence,source_1,source_2
    buf.write("claims,text,rationale,confidence,source_1,source_2\n")
    for c in (art.claims or []):
        s1 = (c.get("sources") or [None, None])[0]
        s2 = (c.get("sources") or [None, None])[1]
        s1v = s1.get("url") if isinstance(s1, dict) else ""
        s2v = s2.get("url") if isinstance(s2, dict) else ""
        row = [
            "",  # section label for symmetry
            esc(c.get("text", "")),
            esc(c.get("rationale", "")),
            c.get("confidence", 0),
            esc(s1v),
            esc(s2v),
        ]
        buf.write(",".join(map(str, row)) + "\n")

    buf.write("\n")

    # Highlights table
    buf.write("highlights_id,dimension,text,start,end,reason,confidence\n")
    for h in highlights:
        data = h.data or {}
        row = [
            h.id,
            esc(h.dimension or ""),
            esc(data.get("text", "")),
            data.get("start", 0),
            data.get("end", 0),
            esc(data.get("reason", "")),
            data.get("confidence", 0),
        ]
        buf.write(",".join(map(str, row)) + "\n")

    buf.seek(0)
    filename = f"article_{article_id}_full_export.csv"
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )