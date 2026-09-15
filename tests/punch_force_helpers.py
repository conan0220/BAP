"""Synthetic two-IMU punching-bag fixtures for deterministic tests.

The waveforms are derived from the rigid-body equations documented by the
repository's ``punch_force`` research reference.  They exist only to exercise
alignment, validation, persistence, and deterministic computation; they are
not real measurements and must not be used as Force Plate accuracy evidence.
"""

from __future__ import annotations

import csv
import io
import math

from bap_common.imu_csv import COMMON_IMU_CSV_HEADER


def synthetic_force_pair(
    *, strikes=(3.0,), sample_rate=400, duration=4.2,
    missing_top=frozenset(), missing_bottom=frozenset(),
):
    count = int(sample_rate * duration) + 1
    mass, length, diameter, impact_offset = 36.0, 1.24, 0.335, 0.2
    inertia = mass * (3 * (diameter / 2) ** 2 + length ** 2) / 12
    result = {}
    for role in ("bag_top", "bag_bottom"):
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=COMMON_IMU_CSV_HEADER, lineterminator="\n")
        writer.writeheader()
        missing = missing_top if role == "bag_top" else missing_bottom
        row_index = 0
        for index in range(count):
            if index in missing:
                continue
            seconds = index / sample_rate
            pulse = max(
                (math.cos(abs(seconds - strike) / 0.04 * math.pi / 2) for strike in strikes if abs(seconds - strike) <= 0.04),
                default=0.0,
            )
            center = 50.0 / mass * 9.80665 * pulse
            angular = impact_offset * (50.0 * 9.80665) / inertia * pulse
            difference = angular * length
            x = center + (difference / 2 if role == "bag_top" else -difference / 2)
            row = {name: "" for name in COMMON_IMU_CSV_HEADER}
            row.update(
                sample_index=row_index, packet_index=index,
                elapsed_us=round(seconds * 1_000_000), device_time_ms=round(seconds * 1000),
                frame_type="0x63", acc_x_g=x / 9.80665, acc_y_g=0.0, acc_z_g=1.0,
                gyro_x_dps=0.0, gyro_y_dps=90.0 * pulse, gyro_z_dps=0.0,
                quat_w=1.0, quat_x=0.0, quat_y=0.0, quat_z=0.0,
            )
            writer.writerow(row)
            row_index += 1
        result[role] = stream.getvalue().encode("utf-8")
    return result
