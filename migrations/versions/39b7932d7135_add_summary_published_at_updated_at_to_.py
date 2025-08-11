"""add summary to articles

Revision ID: 39b7932d7135
Revises: 
Create Date: 2025-08-09 14:46:43.224913
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "39b7932d7135"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add 'summary' (TEXT, nullable)
    op.add_column(
        "articles",
        sa.Column("summary", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("articles", "summary")