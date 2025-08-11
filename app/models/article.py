from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    outlet: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True, unique=False)

    # LLM outputs
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scores: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    highlights: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    # NEW: Claims (MVP) persisted on the article as JSON
    # shape: [{text, rationale?, confidence?, sources:[{title?,url}...]}]
    claims: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    # Timestamps
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now()
    )