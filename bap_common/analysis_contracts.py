"""Versioned contracts shared by the Desktop App and Backend analyses."""

from __future__ import annotations

import math
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
        if self.analysis_type == "punch_speed" and self.spec_version == 2:
            if "measurement_start_elapsed_us" not in parameters:
                raise ContractError(
                    "missing_parameter", "拳頭速度缺少正式測量開始時間"
                )
            boundary = parameters["measurement_start_elapsed_us"]
            if (
                isinstance(boundary, bool)
                or not isinstance(boundary, int)
                or boundary <= 0
            ):
                raise ContractError(
                    "invalid_parameter", "正式測量開始時間必須是大於零的整數 microseconds"
                )

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
        if self.analysis_type == "punch_count":
            left = result.get("left_punch_count")
            right = result.get("right_punch_count")
            total = result.get("total_punch_count")
            if any(value is not None and value < 0 for value in (left, right, total)):
                raise ContractError("invalid_result_value", "出拳次數不得小於零")
            if left is not None and right is not None and total != left + right:
                raise ContractError("invalid_result_value", "總拳數必須等於左右手拳數相加")
        if self.analysis_type == "punch_speed" and self.spec_version == 2:
            _validate_punch_speed_result(result)


def _validate_punch_speed_result(result: dict[str, Any]) -> None:
    count_keys = ("left_punch_count", "right_punch_count", "total_punch_count")
    speed_keys = (
        "left_average_speed_mps",
        "left_max_speed_mps",
        "right_average_speed_mps",
        "right_max_speed_mps",
    )
    if any(result[key] < 0 for key in count_keys):
        raise ContractError("invalid_result_value", "拳數不得小於零")
    if any(not math.isfinite(float(result[key])) or result[key] < 0 for key in speed_keys):
        raise ContractError("invalid_result_value", "拳頭速度必須是非負的有限數值")
    if result["total_punch_count"] != result["left_punch_count"] + result["right_punch_count"]:
        raise ContractError("invalid_result_value", "總拳數必須等於左右手拳數相加")

    punches = result["punches"]
    if len(punches) != result["total_punch_count"]:
        raise ContractError("invalid_result_value", "拳數必須與每拳明細數量一致")
    expected_keys = {
        "hand",
        "punch_index",
        "start_elapsed_us",
        "peak_elapsed_us",
        "end_elapsed_us",
        "peak_speed_mps",
    }
    by_hand: dict[str, list[float]] = {"left": [], "right": []}
    previous_peak = -1
    for punch in punches:
        if not isinstance(punch, dict) or set(punch) != expected_keys:
            raise ContractError("invalid_result_value", "每拳明細欄位不正確")
        hand = punch["hand"]
        if hand not in by_hand:
            raise ContractError("invalid_result_value", "每拳明細的手別不正確")
        expected_index = len(by_hand[hand]) + 1
        if (
            isinstance(punch["punch_index"], bool)
            or punch["punch_index"] != expected_index
        ):
            raise ContractError("invalid_result_value", "每隻手的拳序必須從一開始連續增加")
        times = (
            punch["start_elapsed_us"],
            punch["peak_elapsed_us"],
            punch["end_elapsed_us"],
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in times):
            raise ContractError("invalid_result_value", "每拳明細時間必須是非負整數")
        if not times[0] <= times[1] <= times[2]:
            raise ContractError("invalid_result_value", "每拳明細的時間順序不正確")
        if times[1] < previous_peak:
            raise ContractError("invalid_result_value", "每拳明細必須依發生時間排序")
        previous_peak = times[1]
        speed = punch["peak_speed_mps"]
        if (
            isinstance(speed, bool)
            or not isinstance(speed, (int, float))
            or not math.isfinite(float(speed))
            or speed < 0
        ):
            raise ContractError("invalid_result_value", "每拳速度必須是非負的有限數值")
        by_hand[hand].append(float(speed))

    for hand in ("left", "right"):
        speeds = by_hand[hand]
        if result[f"{hand}_punch_count"] != len(speeds):
            raise ContractError("invalid_result_value", "左右手拳數必須與明細一致")
        expected_average = round(sum(speeds) / len(speeds), 3) if speeds else 0.0
        expected_maximum = round(max(speeds), 3) if speeds else 0.0
        if not math.isclose(
            float(result[f"{hand}_average_speed_mps"]), expected_average, abs_tol=0.001
        ) or not math.isclose(
            float(result[f"{hand}_max_speed_mps"]), expected_maximum, abs_tol=0.001
        ):
            raise ContractError("invalid_result_value", "拳頭速度摘要必須能由每拳明細重新算出")


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
            analysis_type="punch_speed",
            spec_version=2,
            display_name="拳頭速度",
            input_roles=wrist_roles,
            parameter_names=("measurement_start_elapsed_us",),
            result_fields=(
                ResultFieldSpecification(name="algorithm_version", value_type=ResultValueType.STRING),
                ResultFieldSpecification(name="left_punch_count", value_type=ResultValueType.INTEGER),
                ResultFieldSpecification(name="right_punch_count", value_type=ResultValueType.INTEGER),
                ResultFieldSpecification(name="total_punch_count", value_type=ResultValueType.INTEGER),
                ResultFieldSpecification(name="left_average_speed_mps", value_type=ResultValueType.NUMBER),
                ResultFieldSpecification(name="left_max_speed_mps", value_type=ResultValueType.NUMBER),
                ResultFieldSpecification(name="right_average_speed_mps", value_type=ResultValueType.NUMBER),
                ResultFieldSpecification(name="right_max_speed_mps", value_type=ResultValueType.NUMBER),
                ResultFieldSpecification(name="punches", value_type=ResultValueType.ARRAY),
            ),
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
