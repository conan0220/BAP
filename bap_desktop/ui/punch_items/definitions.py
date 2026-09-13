"""Data-driven IMU placement requirements for each punch item."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ImuPlacement:
    id: str
    name: str
    wearer: str


@dataclass(frozen=True, slots=True)
class PunchItemDefinition:
    name: str
    analysis_type: str
    description: str
    placements: tuple[ImuPlacement, ...]
    configuration_decided: bool = True
    spec_version: int = 1


WRIST_PLACEMENTS = (
    ImuPlacement("left_wrist", "左手腕", "拳擊手"),
    ImuPlacement("right_wrist", "右手腕", "拳擊手"),
)

PUNCH_ITEM_DEFINITIONS = {
    "出拳次數": PunchItemDefinition("出拳次數", "punch_count", "記錄左右手的出拳動作。", WRIST_PLACEMENTS),
    "拳頭速度": PunchItemDefinition(
        "拳頭速度",
        "punch_speed",
        "指定左右手腕 IMU，計算每一拳的拳頭速度。",
        WRIST_PLACEMENTS,
        spec_version=2,
    ),
    "出拳力量": PunchItemDefinition(
        "出拳力量",
        "punch_force",
        "所需 IMU 數量與安裝位置尚未決定。",
        (),
        configuration_decided=False,
    ),
    "出拳軌跡": PunchItemDefinition(
        "出拳軌跡",
        "punch_trajectory",
        "指定左右手腕 IMU，以互動式 3D 圖查看每一拳的動作路徑。",
        WRIST_PLACEMENTS,
        spec_version=2,
    ),
    "拳種辨識": PunchItemDefinition(
        "拳種辨識",
        "punch_classification",
        "由持靶人左右拳靶背面的 IMU 記錄擊打動作。",
        (
            ImuPlacement("holder_left_pad", "左手拳靶背面", "持靶人"),
            ImuPlacement("holder_right_pad", "右手拳靶背面", "持靶人"),
        ),
        spec_version=2,
    ),
}


def get_punch_item_definition(name: str) -> PunchItemDefinition:
    return PUNCH_ITEM_DEFINITIONS[name]
