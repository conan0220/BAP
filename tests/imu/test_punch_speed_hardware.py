"""Manual acceptance record for punch-speed tests that require physical IMUs."""

from __future__ import annotations

import os

import pytest


@pytest.mark.hardware
@pytest.mark.scenario("punch-speed-analysis", "user 進行實際 IMU 測試")
def test_user_confirms_real_punch_speed_behavior_without_ground_truth() -> None:
    """Run only after the user completes tasks 8.1 through 8.3.

    The explicit environment variable prevents CI or a developer from accidentally
    claiming that physical hardware validation happened on a machine without IMUs.
    """

    assert os.environ.get("BAP_PUNCH_SPEED_HARDWARE_CONFIRMED") == "1", (
        "請先依 tasks.md 8.1～8.3 完成實際雙 IMU 驗證；確認後再以 "
        "BAP_PUNCH_SPEED_HARDWARE_CONFIRMED=1 執行此 hardware test。"
    )
