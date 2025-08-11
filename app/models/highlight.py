from sqlalchemy import Column, Integer, ForeignKey, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.db import Base

class Highlight(Base):
    __tablename__ = "highlights"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)

    # bias dimension this phrase influenced (e.g., 'framing_choices', 'emotional_tone')
    dimension = Column(String(64), nullable=False)

    # Store the actual snippet + metadata
    # Example: {"text":"critics say","start":102,"end":113,"reason":"vague attribution","confidence":0.72}
    data = Column(JSONB, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())