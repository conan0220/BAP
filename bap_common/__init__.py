"""Shared BAP infrastructure that has no Qt or FastAPI dependency."""

from .analysis_contracts import (
    AnalysisSpecification,
    ContractError,
    InputRoleSpecification,
    ResultFieldSpecification,
    ResultValueType,
    builtin_analysis_specifications,
)
from .analysis_session import (
    AnalysisInputBinding,
    AnalysisJobRequest,
    CsvDescriptor,
    ImuSourceDescriptor,
    SessionMetadata,
    SourceConnectionType,
)
from .imu_csv import COMMON_IMU_CSV_HEADER, COMMON_IMU_CSV_VERSION
from .logging import configure_logging, safe_log_event

__all__ = [
    "AnalysisInputBinding",
    "AnalysisJobRequest",
    "AnalysisSpecification",
    "COMMON_IMU_CSV_HEADER",
    "COMMON_IMU_CSV_VERSION",
    "ContractError",
    "CsvDescriptor",
    "ImuSourceDescriptor",
    "InputRoleSpecification",
    "ResultFieldSpecification",
    "ResultValueType",
    "builtin_analysis_specifications",
    "SessionMetadata",
    "SourceConnectionType",
    "configure_logging",
    "safe_log_event",
]
