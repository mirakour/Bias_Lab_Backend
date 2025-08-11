from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.highlight import Highlight

router = APIRouter(prefix="/highlights", tags=["highlights"])

class HighlightCreate(BaseModel):
    article_id: int
    dimension: str
    data: Dict[str, Any]

class HighlightUpdate(BaseModel):
    dimension: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

class HighlightOut(BaseModel):
    id: int
    article_id: int
    dimension: str
    data: Dict[str, Any]

    class Config:
        from_attributes = True

@router.get("", response_model=List[HighlightOut])
async def list_highlights(
    article_id: Optional[int] = Query(default=None),
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Highlight).order_by(Highlight.id.desc()).limit(limit)
    if article_id is not None:
        stmt = select(Highlight).where(Highlight.article_id == article_id).order_by(Highlight.id.desc()).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/{highlight_id}", response_model=HighlightOut)
async def get_highlight(highlight_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(Highlight, highlight_id)
    if not row:
        raise HTTPException(status_code=404, detail="Highlight not found")
    return row

@router.post("", response_model=HighlightOut, status_code=201)
async def create_highlight(payload: HighlightCreate, db: AsyncSession = Depends(get_db)):
    row = Highlight(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row

@router.patch("/{highlight_id}", response_model=HighlightOut)
async def update_highlight(highlight_id: int, payload: HighlightUpdate, db: AsyncSession = Depends(get_db)):
    row = await db.get(Highlight, highlight_id)
    if not row:
        raise HTTPException(status_code=404, detail="Highlight not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row

@router.delete("/{highlight_id}", status_code=204)
async def delete_highlight(highlight_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(Highlight, highlight_id)
    if not row:
        raise HTTPException(status_code=404, detail="Highlight not found")
    await db.delete(row)
    await db.commit()