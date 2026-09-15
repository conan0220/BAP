"""Exercise the production punch-force Executor over real Candidate HTTP."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from bap_common.analysis_session import (
    AnalysisInputBinding,
    AnalysisJobRequest,
    CsvDescriptor,
    ImuSourceDescriptor,
    SessionMetadata,
    SessionStopReason,
    SourceConnectionType,
)
from bap_common.imu_csv import COMMON_IMU_CSV_HEADER, inspect_common_imu_csv_bytes


def _csv(
    role: str,
    *,
    strikes: tuple[float, ...] = (3.0,),
    sample_rate: int = 400,
    missing: frozenset[int] = frozenset(),
) -> bytes:
    mass, length, diameter, impact_offset = 36.0, 1.24, 0.335, 0.2
    inertia = mass * (3.0 * (diameter / 2.0) ** 2 + length**2) / 12.0
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COMMON_IMU_CSV_HEADER, lineterminator="\n")
    writer.writeheader()
    row_index = 0
    for packet in range(int(sample_rate * 4.2) + 1):
        if packet in missing:
            continue
        seconds = packet / sample_rate
        pulse = max(
            (
                math.cos(abs(seconds - strike) / 0.04 * math.pi / 2.0)
                for strike in strikes
                if abs(seconds - strike) <= 0.04
            ),
            default=0.0,
        )
        center = 50.0 / mass * 9.80665 * pulse
        angular = impact_offset * (50.0 * 9.80665) / inertia * pulse
        difference = angular * length
        horizontal = center + (difference / 2.0 if role == "bag_top" else -difference / 2.0)
        row = {name: "" for name in COMMON_IMU_CSV_HEADER}
        row.update(
            sample_index=row_index,
            packet_index=packet,
            elapsed_us=round(seconds * 1_000_000),
            device_time_ms=round(seconds * 1000),
            frame_type="0x63",
            acc_x_g=horizontal / 9.80665,
            acc_y_g=0.0,
            acc_z_g=1.0,
            gyro_x_dps=0.0,
            gyro_y_dps=90.0 * pulse,
            gyro_z_dps=0.0,
            quat_w=1.0,
            quat_x=0.0,
            quat_y=0.0,
            quat_z=0.0,
        )
        writer.writerow(row)
        row_index += 1
    return stream.getvalue().encode("utf-8")


def _package(case: str) -> tuple[SessionMetadata, dict[str, bytes]]:
    strikes: tuple[float, ...] = (3.0,)
    sample_rate = 400
    missing_top: frozenset[int] = frozenset()
    if case == "no_strike":
        strikes = ()
    elif case == "multiple_strikes":
        strikes = (2.8, 3.4)
    elif case == "warning":
        sample_rate = 125
    elif case == "packet_gap":
        missing_top = frozenset(range(1000, 1006))

    contents = {
        "bag-top.csv": _csv("bag_top", strikes=strikes, sample_rate=sample_rate, missing=missing_top),
        "bag-bottom.csv": _csv("bag_bottom", strikes=strikes, sample_rate=sample_rate),
    }
    descriptors = []
    for node_id, (filename, data) in enumerate(contents.items()):
        inspected = inspect_common_imu_csv_bytes(data)
        group_id = 1 if case == "different_group" and node_id == 1 else 0
        descriptors.append(CsvDescriptor(
            csv_id=uuid4(),
            filename=filename,
            source=ImuSourceDescriptor(
                source_id=f"CI:group-{group_id}:node-{node_id}",
                port="CI",
                connection_type=SourceConnectionType.WIRELESS_RECEIVER,
                baud_rate=921600,
                group_id=group_id,
                node_id=node_id,
            ),
            row_count=inspected.row_count,
            size_bytes=inspected.size_bytes,
            sha256=inspected.sha256,
        ))
    job = AnalysisJobRequest(
        analysis_id=uuid4(),
        analysis_type="punch_force",
        spec_version=1,
        input_bindings=(
            AnalysisInputBinding(input_role="bag_top", csv_id=descriptors[0].csv_id),
            AnalysisInputBinding(input_role="bag_bottom", csv_id=descriptors[1].csv_id),
        ),
        parameters={
            "calibration_end_elapsed_us": 2_000_000,
            "measurement_start_elapsed_us": 2_200_000,
            "bag_mass_kg": 36.0,
            "bag_length_m": 1.24,
            "bag_diameter_m": 0.335,
            "sensor_distance_m": 1.24,
        },
    )
    now = datetime.now(timezone.utc)
    return SessionMetadata(
        session_id=uuid4(),
        metadata_schema_version=2,
        desktop_version="0.0.0-ci",
        started_at=now,
        ended_at=now,
        requested_duration_seconds=5,
        actual_duration_seconds=4.2,
        stop_reason=SessionStopReason.DURATION_REACHED,
        csv_files=tuple(descriptors),
        analyses=(job,),
    ), contents


def _run_case(client: httpx.Client, headers: dict[str, str], case: str) -> dict:
    metadata, contents = _package(case)
    response = client.post(
        "v1/measurement-sessions",
        headers=headers,
        data={"metadata": metadata.canonical_json()},
        files=[("files", (name, data, "text/csv")) for name, data in contents.items()],
    )
    response.raise_for_status()
    analysis_id = metadata.analyses[0].analysis_id
    payload: dict | None = None
    for _attempt in range(60):
        status = client.get(
            f"v1/measurement-sessions/{metadata.session_id}/analyses/{analysis_id}",
            headers=headers,
        )
        status.raise_for_status()
        payload = status.json()
        if payload["status"] not in {"pending", "processing"}:
            break
        time.sleep(0.25)
    if payload is None or payload["status"] in {"pending", "processing"}:
        raise RuntimeError(f"punch-force case timed out: {case}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args(argv)
    base = args.api_base_url.rstrip("/") + "/"
    expected_failures = {
        "no_strike": "no_valid_strike",
        "multiple_strikes": "multiple_strikes",
        "packet_gap": "packet_alignment_failed",
        "different_group": "different_gateway",
    }
    with httpx.Client(base_url=base, timeout=60.0) as client:
        login = client.post("v1/auth/login", json={"username": args.username, "password": args.password})
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        capabilities = client.get("v1/analysis-capabilities", headers=headers)
        capabilities.raise_for_status()
        capability = next(
            item for item in capabilities.json()["capabilities"]
            if item["analysis_type"] == "punch_force" and item["spec_version"] == 1
        )
        if not capability["executable"]:
            raise RuntimeError("punch_force version 1 is not executable")

        valid = _run_case(client, headers, "valid")
        if valid["status"] != "completed":
            raise RuntimeError(f"valid punch-force case failed: {valid}")
        result = valid["result"]
        if result["algorithm_version"] != "bag_rigid_body_v1" or result["peak_force_kgf"] <= 0:
            raise RuntimeError("valid punch-force result was incomplete")
        if len(result["curve_points"]) > 300:
            raise RuntimeError("punch-force curve exceeded display limit")

        warning = _run_case(client, headers, "warning")
        if warning["status"] != "completed" or warning["result"]["quality_status"] != "warning":
            raise RuntimeError(f"warning punch-force case did not remain visible: {warning}")

        for case, expected_code in expected_failures.items():
            failed = _run_case(client, headers, case)
            if failed["status"] != "failed" or failed.get("error_code") != expected_code:
                raise RuntimeError(f"unexpected punch-force failure for {case}: {failed}")
            if "Traceback" in (failed.get("safe_error_message") or ""):
                raise RuntimeError(f"unsafe punch-force error for {case}")

        print(json.dumps({
            "status": "passed",
            "algorithm_version": result["algorithm_version"],
            "cases": ["valid", "warning", *expected_failures],
        }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
