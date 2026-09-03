"""Add the tested Source Tree SHA to Desktop release metadata."""

from alembic import op
import sqlalchemy as sa


revision = "0002_app_release_source_tree_sha"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_releases",
        sa.Column("source_tree_sha", sa.String(40), nullable=False, server_default="unknown"),
    )


def downgrade() -> None:
    op.drop_column("app_releases", "source_tree_sha")
