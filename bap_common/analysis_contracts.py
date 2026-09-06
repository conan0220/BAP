"""Versioned contracts shared by the Desktop App and Backend analyses."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator


ANALYSIS_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
ROLE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class ContractError(ValueError):
    """A stable validation error safe to surface through an API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ResultValueType(StrEnum):
    INTEGER = "integer"
    NUMBER = "number"
    STRING = "string"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"


class InputRoleSpecification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    display_name: str
    data_type: str = "imu_csv"
    required: bool = True
    quantity: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_name(self) -> "InputRoleSpecification":
        if not ROLE_PATTERN.fullmatch(self.name):
            raise ValueError("Input Role 名稱格式不正確")
        if self.data_type != "imu_csv":
            raise ValueError("目前只支援 imu_csv Input Role")
        return self


class ResultFieldSpecification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    value_type: ResultValueType
    required: bool = True

    @model_validator(mode="after")
    def validate_name(self) -> "ResultFieldSpecification":
        if not ROLE_PATTERN.fullmatch(self.name):
            raise ValueError("Result 欄位名稱格式不正確")
        return self


class AnalysisSpecification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_type: str
    spec_version: int = Field(ge=1)
    display_name: str
    input_roles: tuple[InputRoleSpecification, ...]
    parameter_names: tuple[str, ...] = ()
    result_fields: tuple[ResultFieldSpecification, ...]
    allow_same_csv_for_multiple_roles: bool = False

    @model_validator(mode="after")
    def validate_contract(self) -> "AnalysisSpecification":
        if not ANALYSIS_TYPE_PATTERN.fullmatch(self.analysis_type):
            raise ValueError("Analysis Type 格式不正確")
        role_names = [role.name for role in self.input_roles]
        if len(role_names) != len(set(role_names)):
            raise ValueError("Input Role 不得重複")
        result_names = [field.name for field in self.result_fields]
        if len(result_names) != len(set(result_names)):
            raise ValueError("Result 欄位不得重複")
        if len(self.parameter_names) != len(set(self.parameter_names)):
            raise ValueError("Parameter 名稱不得重複")
        for name in self.parameter_names:
            if not ROLE_PATTERN.fullmatch(name):
                raise ValueError("Parameter 名稱格式不正確")
        return self

    def validate_inputs(self, bindings: Iterable[Any], available_csv_ids: set[str]) -> None:
        bindings = tuple(bindings)
        by_role: dict[str, list[Any]] = {}
        for binding in bindings:
            role = str(binding.input_role)
            by_role.setdefault(role, []).append(binding)
            if str(binding.csv_id) not in available_csv_ids:
                raise ContractError("unknown_csv", f"Input Role {role} 引用了不屬於本 Session 的 CSV")

        known_roles = {role.name: role for role in self.input_roles}
        unknown = sorted(set(by_role) - set(known_roles))
        if unknown:
            raise ContractError("unknown_input_role", f"未知的 Input Role：{', '.join(unknown)}")

        for role_name, role in known_roles.items():
            count = len(by_role.get(role_name, ()))
            if role.required and count == 0:
                raise ContractError("missing_input_role", f"缺少必要 Input Role：{role_name}")
            if count > role.quantity:
                raise ContractError("duplicate_input_role", f"Input Role {role_name} 的資料數量超過規格")

        csv_ids = [str(binding.csv_id) for binding in bindings]
        if not self.allow_same_csv_for_multiple_roles and len(csv_ids) != len(set(csv_ids)):
            raise ContractError("duplicate_csv_binding", "同一份 CSV 不能同時用於多個 Input Roles")

    def validate_parameters(self, parameters: dict[str, Any]) -> None:
        unknown = sorted(set(parameters) - set(self.parameter_names))
        if unknown:
            raise ContractError("unknown_parameter", f"未知的 Analysis Parameter：{', '.join(unknown)}")

    def validate_result(self, result: dict[str, Any]) -> None:
        fields = {field.name: field for field in self.result_fields}
        unknown = sorted(set(result) - set(fields))
        if unknown:
            raise ContractError("unknown_result_field", f"未知的 Result 欄位：{', '.join(unknown)}")
        for name, field in fields.items():
            if field.required and name not in result:
                raise ContractError("missing_result_field", f"缺少 Result 欄位：{name}")
            if name in result and not _matches_type(result[name], field.value_type):
                raise ContractError("invalid_result_type", f"Result 欄位 {name} 的型別不正確")


def _matches_type(value: Any, expected: ResultValueType) -> bool:
    if expected is ResultValueType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected is ResultValueType.NUMBER:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected is ResultValueType.STRING:
        return isinstance(value, str)
    if expected is ResultValueType.BOOLEAN:
        return isinstance(value, bool)
    if expected is ResultValueType.OBJECT:
        return isinstance(value, dict)
    if expected is ResultValueType.ARRAY:
        return isinstance(value, list)
    return False


def builtin_analysis_specifications() -> tuple[AnalysisSpecification, ...]:
    """Contracts understood by this Desktop version; executors are separate."""

    wrist_roles = (
        InputRoleSpecification(name="left_wrist", display_name="左手腕"),
        InputRoleSpecification(name="right_wrist", display_name="右手腕"),
    )
    return (
        AnalysisSpecification(
            analysis_type="punch_count",
            spec_version=1,
            display_name="出拳次數",
            input_roles=wrist_roles,
            result_fields=(
                ResultFieldSpecification(name="left_punch_count", value_type=ResultValueType.INTEGER),
                ResultFieldSpecification(name="right_punch_count", value_type=ResultValueType.INTEGER),
                ResultFieldSpecification(name="total_punch_count", value_type=ResultValueType.INTEGER),
            ),
        ),
        AnalysisSpecification(
            analysis_type="punch_speed", spec_version=1, display_name="出拳速度",
            input_roles=wrist_roles,
            result_fields=(ResultFieldSpecification(name="summary", value_type=ResultValueType.OBJECT),),
        ),
        AnalysisSpecification(
            analysis_type="punch_trajectory", spec_version=1, display_name="出拳軌跡",
            input_roles=wrist_roles,
            result_fields=(ResultFieldSpecification(name="summary", value_type=ResultValueType.OBJECT),),
        ),
        AnalysisSpecification(
            analysis_type="punch_classification", spec_version=1, display_name="拳種辨識",
            input_roles=(
                InputRoleSpecification(name="holder_left_pad", display_name="持靶人左手靶"),
                InputRoleSpecification(name="holder_right_pad", display_name="持靶人右手靶"),
            ),
            result_fields=(ResultFieldSpecification(name="summary", value_type=ResultValueType.OBJECT),),
        ),
    )
