"""add claims to articles"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a998db096cd2"
down_revision: Union[str, Sequence[str], None] = "a2565a9b875b"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column(
            "claims",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.alter_column("articles", "claims", server_default=None)

def downgrade() -> None:
    op.drop_column("articles", "claims")
