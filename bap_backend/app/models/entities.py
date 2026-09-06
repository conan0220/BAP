"""BAP persistence models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bap_backend.app.db.base import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    username: Mapped[str] = mapped_column(String(64, collation="BINARY"), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    refresh_sessions: Mapped[list["RefreshSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    measurement_sessions: Mapped[list["MeasurementSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped[User] = relationship(back_populates="refresh_sessions")


class AppRelease(Base):
    __tablename__ = "app_releases"
    __table_args__ = (UniqueConstraint("platform", "version", name="uq_release_platform_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[str] = mapped_column(String(32))
    download_url: Mapped[str] = mapped_column(String(2048))
    sha256: Mapped[str] = mapped_column(String(64))
    source_tree_sha: Mapped[str] = mapped_column(String(40))
    published_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class MeasurementSession(Base):
    __tablename__ = "measurement_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    package_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="accepted", index=True)
    metadata_schema_version: Mapped[int] = mapped_column(Integer)
    imu_csv_schema_version: Mapped[int] = mapped_column(Integer)
    desktop_version: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="measurement_sessions")
    csv_files: Mapped[list["ImuCsvFile"]] = relationship(
        back_populates="measurement_session", cascade="all, delete-orphan"
    )
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(
        back_populates="measurement_session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "package_fingerprint", name="uq_session_user_fingerprint"),
        UniqueConstraint("id", "user_id", name="uq_session_id_user"),
    )


class ImuCsvFile(Base):
    __tablename__ = "imu_csv_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("measurement_sessions.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    source_id: Mapped[str] = mapped_column(String(255))
    port: Mapped[str] = mapped_column(String(255))
    connection_type: Mapped[str] = mapped_column(String(32))
    baud_rate: Mapped[int] = mapped_column(Integer)
    group_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    csv_blob: Mapped[bytes] = mapped_column(LargeBinary)

    measurement_session: Mapped[MeasurementSession] = relationship(back_populates="csv_files")
    input_bindings: Mapped[list["AnalysisInputBindingEntity"]] = relationship(
        back_populates="csv_file", overlaps="analysis_job,input_bindings"
    )

    __table_args__ = (
        UniqueConstraint("session_id", "filename", name="uq_csv_session_filename"),
        UniqueConstraint("session_id", "id", name="uq_csv_session_id"),
    )


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("measurement_sessions.id", ondelete="CASCADE"), index=True
    )
    analysis_type: Mapped[str] = mapped_column(String(64), index=True)
    spec_version: Mapped[int] = mapped_column(Integer)
    parameters_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safe_error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    measurement_session: Mapped[MeasurementSession] = relationship(back_populates="analysis_jobs")
    input_bindings: Mapped[list["AnalysisInputBindingEntity"]] = relationship(
        back_populates="analysis_job", cascade="all, delete-orphan", overlaps="csv_file,input_bindings"
    )
    result: Mapped["AnalysisResult | None"] = relationship(
        back_populates="analysis_job", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (UniqueConstraint("session_id", "id", name="uq_analysis_session_id"),)


class AnalysisInputBindingEntity(Base):
    __tablename__ = "analysis_input_bindings"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    input_role: Mapped[str] = mapped_column(String(64), primary_key=True)
    csv_id: Mapped[str] = mapped_column(String(36), nullable=False)

    analysis_job: Mapped[AnalysisJob] = relationship(
        back_populates="input_bindings", overlaps="csv_file,input_bindings"
    )
    csv_file: Mapped[ImuCsvFile] = relationship(
        back_populates="input_bindings", overlaps="analysis_job,input_bindings"
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "analysis_id"],
            ["analysis_jobs.session_id", "analysis_jobs.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["session_id", "csv_id"],
            ["imu_csv_files.session_id", "imu_csv_files.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("analysis_id", "csv_id", name="uq_binding_analysis_csv"),
    )


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    analysis_job: Mapped[AnalysisJob] = relationship(back_populates="result")
