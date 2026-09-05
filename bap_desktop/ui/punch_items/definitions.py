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
    description: str
    placements: tuple[ImuPlacement, ...]
    configuration_decided: bool = True


WRIST_PLACEMENTS = (
    ImuPlacement("left_wrist", "左手腕", "拳擊手"),
    ImuPlacement("right_wrist", "右手腕", "拳擊手"),
)

PUNCH_ITEM_DEFINITIONS = {
    "出拳次數": PunchItemDefinition("出拳次數", "記錄左右手的出拳動作。", WRIST_PLACEMENTS),
    "出拳速度": PunchItemDefinition("出拳速度", "比較左右手的出拳速度。", WRIST_PLACEMENTS),
    "出拳力量": PunchItemDefinition(
        "出拳力量",
        "所需 IMU 數量與安裝位置尚未決定。",
        (),
        configuration_decided=False,
    ),
    "出拳軌跡": PunchItemDefinition("出拳軌跡", "記錄左右手的動作路徑。", WRIST_PLACEMENTS),
    "拳種辨識": PunchItemDefinition(
        "拳種辨識",
        "由持把人左右手把背面的 IMU 記錄擊打動作。",
        (
            ImuPlacement("holder_left_pad", "左手把背面", "持把人"),
            ImuPlacement("holder_right_pad", "右手把背面", "持把人"),
        ),
    ),
}


def get_punch_item_definition(name: str) -> PunchItemDefinition:
    return PUNCH_ITEM_DEFINITIONS[name]
