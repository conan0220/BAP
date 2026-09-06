"""Add measurement Sessions, Common IMU CSV files, jobs, bindings, and results."""

from alembic import op
import sqlalchemy as sa


revision = "0003_analysis_sessions"
down_revision = "0002_app_release_source_tree_sha"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "measurement_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("package_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("metadata_schema_version", sa.Integer, nullable=False),
        sa.Column("imu_csv_schema_version", sa.Integer, nullable=False),
        sa.Column("desktop_version", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("ended_at", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("user_id", "package_fingerprint", name="uq_session_user_fingerprint"),
        sa.UniqueConstraint("id", "user_id", name="uq_session_id_user"),
    )
    op.create_index("ix_measurement_sessions_user_id", "measurement_sessions", ["user_id"])
    op.create_index("ix_measurement_sessions_status", "measurement_sessions", ["status"])

    op.create_table(
        "imu_csv_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("measurement_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("port", sa.String(255), nullable=False),
        sa.Column("connection_type", sa.String(32), nullable=False),
        sa.Column("baud_rate", sa.Integer, nullable=False),
        sa.Column("group_id", sa.Integer, nullable=True),
        sa.Column("node_id", sa.Integer, nullable=True),
        sa.Column("row_count", sa.Integer, nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("csv_blob", sa.LargeBinary, nullable=False),
        sa.UniqueConstraint("session_id", "filename", name="uq_csv_session_filename"),
        sa.UniqueConstraint("session_id", "id", name="uq_csv_session_id"),
    )
    op.create_index("ix_imu_csv_files_session_id", "imu_csv_files", ["session_id"])

    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("measurement_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_type", sa.String(64), nullable=False),
        sa.Column("spec_version", sa.Integer, nullable=False),
        sa.Column("parameters_json", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("safe_error_message", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("session_id", "id", name="uq_analysis_session_id"),
    )
    op.create_index("ix_analysis_jobs_session_id", "analysis_jobs", ["session_id"])
    op.create_index("ix_analysis_jobs_analysis_type", "analysis_jobs", ["analysis_type"])
    op.create_index("ix_analysis_jobs_status", "analysis_jobs", ["status"])

    op.create_table(
        "analysis_input_bindings",
        sa.Column("session_id", sa.String(36), primary_key=True),
        sa.Column("analysis_id", sa.String(36), primary_key=True),
        sa.Column("input_role", sa.String(64), primary_key=True),
        sa.Column("csv_id", sa.String(36), nullable=False),
        sa.ForeignKeyConstraint(["session_id", "analysis_id"], ["analysis_jobs.session_id", "analysis_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id", "csv_id"], ["imu_csv_files.session_id", "imu_csv_files.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("analysis_id", "csv_id", name="uq_binding_analysis_csv"),
    )
    op.create_table(
        "analysis_results",
        sa.Column("analysis_id", sa.String(36), sa.ForeignKey("analysis_jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("result_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("analysis_results")
    op.drop_table("analysis_input_bindings")
    op.drop_index("ix_analysis_jobs_status", table_name="analysis_jobs")
    op.drop_index("ix_analysis_jobs_analysis_type", table_name="analysis_jobs")
    op.drop_index("ix_analysis_jobs_session_id", table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
    op.drop_index("ix_imu_csv_files_session_id", table_name="imu_csv_files")
    op.drop_table("imu_csv_files")
    op.drop_index("ix_measurement_sessions_status", table_name="measurement_sessions")
    op.drop_index("ix_measurement_sessions_user_id", table_name="measurement_sessions")
    op.drop_table("measurement_sessions")
