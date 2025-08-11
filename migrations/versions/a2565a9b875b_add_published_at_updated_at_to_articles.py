"""add published_at & updated_at to articles

Revision ID: a2565a9b875b
Revises: 39b7932d7135
Create Date: 2025-08-09 15:01:18.747672
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a2565a9b875b"
down_revision: Union[str, Sequence[str], None] = "39b7932d7135"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema (idempotent if columns already exist)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("articles")}

    if "published_at" not in existing_cols:
        op.add_column(
            "articles",
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "updated_at" not in existing_cols:
        op.add_column(
            "articles",
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    """Downgrade schema (safe even if columns missing)."""
    # Postgres supports IF EXISTS; this keeps downgrade resilient.
    op.execute('ALTER TABLE articles DROP COLUMN IF EXISTS "updated_at"')
    op.execute('ALTER TABLE articles DROP COLUMN IF EXISTS "published_at"')
