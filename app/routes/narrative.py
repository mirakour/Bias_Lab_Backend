from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy import select, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.narrative import Narrative
from app.models.article import Article  # used by /cluster
from datetime import datetime, timezone

router = APIRouter(prefix="/narratives", tags=["narratives"])

# ---------- Schemas ----------
class NarrativeCreate(BaseModel):
    label: str
    data: Optional[Dict[str, Any]] = None  # e.g. {"article_ids":[1,2,3], "summary":"..."}

class NarrativeUpdate(BaseModel):
    label: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

class NarrativeOut(BaseModel):
    id: int
    label: str
    data: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True

# ---------- CRUD ----------
@router.get("", response_model=List[NarrativeOut])
async def list_narratives(
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Narrative)
    stmt = stmt.order_by(desc(Narrative.id) if order == "desc" else asc(Narrative.id)).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/{narrative_id}", response_model=NarrativeOut)
async def get_narrative(narrative_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(Narrative, narrative_id)
    if not row:
        raise HTTPException(status_code=404, detail="Narrative not found")
    return row

@router.post("", response_model=NarrativeOut, status_code=201)
async def create_narrative(payload: NarrativeCreate, db: AsyncSession = Depends(get_db)):
    row = Narrative(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row

@router.patch("/{narrative_id}", response_model=NarrativeOut)
async def update_narrative(narrative_id: int, payload: NarrativeUpdate, db: AsyncSession = Depends(get_db)):
    row = await db.get(Narrative, narrative_id)
    if not row:
        raise HTTPException(status_code=404, detail="Narrative not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row

@router.delete("/{narrative_id}", status_code=204)
async def delete_narrative(narrative_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(Narrative, narrative_id)
    if not row:
        raise HTTPException(status_code=404, detail="Narrative not found")
    await db.delete(row)
    await db.commit()
    return None

# ---------- Simple clustering to auto-create narratives ----------
def _tokens(s: str) -> set[str]:
    import re
    toks = re.findall(r"[A-Za-z0-9]+", (s or "").lower())
    stop = {"the","a","an","and","or","to","of","for","in","on","with","at","by","from","about"}
    return {t for t in toks if t not in stop and len(t) > 2}

def _sim(a: set[str], b: set[str]) -> float:
    if not a or not b: return 0.0
    inter = len(a & b); union = len(a | b)
    return inter/union

@router.post("/cluster", response_model=List[NarrativeOut])
async def cluster_narratives(
    window: int = Query(50, ge=5, le=200),
    threshold: float = Query(0.35, ge=0.1, le=0.9),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Article).order_by(Article.id.desc()).limit(window))
    arts = list(result.scalars().all())
    if not arts: return []

    buckets: list[dict] = []
    for a in arts:
        t = _tokens(a.title or a.url or f"article-{a.id}")
        placed = False
        for b in buckets:
            if _sim(t, b["tokens"]) >= threshold:
                b["tokens"] |= t
                b["ids"].append(a.id)
                placed = True
                break
        if not placed:
            buckets.append({"tokens": set(t), "ids": [a.id]})

    outs: list[Narrative] = []
    for b in buckets:
        ids = sorted(set(b["ids"]), reverse=True)
        if not ids: continue
        rep = next((a for a in arts if a.id == ids[0]), None)
        label = (rep.title if rep and rep.title else "Narrative")
        if b["tokens"]:
            top = sorted(b["tokens"], key=lambda x: (-len(x), x))[:3]
            label = " / ".join(top).title()
        n = Narrative(
            label=label,
            data={
                "article_ids": ids,
                "summary": f"Cluster of {len(ids)} related stories.",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.add(n); outs.append(n)

    await db.commit()
    for n in outs: await db.refresh(n)
    return outs