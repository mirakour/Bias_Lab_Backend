from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.db import Base

class Narrative(Base):
    __tablename__ = "narratives"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(256), nullable=False)
    # free-form JSON for now: can include article_ids, centroid, sparkline, etc.
    data = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())