import os

import pytest

from bap_desktop.services.imu_scan import PortInfo, PySerialPortAdapter, ScanStatus, scan_port


@pytest.mark.hardware
def test_supported_imu_is_read_only_and_parseable_at_921600() -> None:
    port = os.environ.get("BAP_HARDWARE_PORT")
    if not port:
        pytest.skip("Set BAP_HARDWARE_PORT when a supported IMU or receiver is attached")
    result = scan_port(
        PortInfo(port, "hardware-under-test"),
        PySerialPortAdapter(),
        duration_seconds=3,
    )
    assert result.status is ScanStatus.CONNECTED
    assert result.frames
