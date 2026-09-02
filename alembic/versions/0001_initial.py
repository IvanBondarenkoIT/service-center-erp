"""Initial schema baseline.

App also runs Base.metadata.create_all on startup for local/demo speed.
Use Alembic for production schema evolution.
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tables are created by SQLAlchemy metadata on startup for MVP.
    # This revision documents the baseline; generate diffs with:
    #   alembic revision --autogenerate -m "..."
    pass


def downgrade() -> None:
    pass
