"""Add nullable Session duration and stop reason fields."""

from alembic import op
import sqlalchemy as sa


revision = "0004_session_duration_metadata"
down_revision = "0003_analysis_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "measurement_sessions",
        sa.Column("requested_duration_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "measurement_sessions",
        sa.Column("actual_duration_seconds", sa.Float(), nullable=True),
    )
    op.add_column(
        "measurement_sessions",
        sa.Column("stop_reason", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("measurement_sessions", "stop_reason")
    op.drop_column("measurement_sessions", "actual_duration_seconds")
    op.drop_column("measurement_sessions", "requested_duration_seconds")
