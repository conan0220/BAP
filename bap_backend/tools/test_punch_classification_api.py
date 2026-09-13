"""Run a production-executor punch-classification smoke test over real HTTP."""

from __future__ import annotations

import argparse
import csv
import io
import json
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


def _csv(node_id: int) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(COMMON_IMU_CSV_HEADER)
    for index in range(400):
        writer.writerow((
            index, index, index * 2500, 10_000 + index, "0x91",
            0.01 + node_id * 0.001, 0.02, 1.0,
            0.1, 0.2, 0.3,
            1.0, 2.0, 3.0,
            0.0, 0.0, 0.0,
            1.0, 0.0, 0.0, 0.0,
            "", "",
        ))
    return stream.getvalue().encode("utf-8")


def _package() -> tuple[SessionMetadata, dict[str, bytes]]:
    contents = {"holder-left.csv": _csv(0), "holder-right.csv": _csv(1)}
    descriptors = []
    for node_id, (filename, data) in enumerate(contents.items()):
        inspected = inspect_common_imu_csv_bytes(data)
        descriptors.append(CsvDescriptor(
            csv_id=uuid4(),
            filename=filename,
            source=ImuSourceDescriptor(
                source_id=f"CI:group-1:node-{node_id}",
                port="CI",
                connection_type=SourceConnectionType.WIRELESS_RECEIVER,
                baud_rate=921600,
                group_id=1,
                node_id=node_id,
            ),
            row_count=inspected.row_count,
            size_bytes=inspected.size_bytes,
            sha256=inspected.sha256,
        ))
    analysis = AnalysisJobRequest(
        analysis_id=uuid4(),
        analysis_type="punch_classification",
        spec_version=2,
        input_bindings=(
            AnalysisInputBinding(input_role="holder_left_pad", csv_id=descriptors[0].csv_id),
            AnalysisInputBinding(input_role="holder_right_pad", csv_id=descriptors[1].csv_id),
        ),
    )
    now = datetime.now(timezone.utc)
    metadata = SessionMetadata(
        session_id=uuid4(),
        metadata_schema_version=2,
        desktop_version="0.0.0-ci",
        started_at=now,
        ended_at=now,
        requested_duration_seconds=5,
        actual_duration_seconds=1.0,
        stop_reason=SessionStopReason.DURATION_REACHED,
        csv_files=tuple(descriptors),
        analyses=(analysis,),
    )
    return metadata, contents


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args(argv)
    base = args.api_base_url.rstrip("/") + "/"
    with httpx.Client(base_url=base, timeout=60.0) as client:
        login = client.post("v1/auth/login", json={"username": args.username, "password": args.password})
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        capabilities = client.get("v1/analysis-capabilities", headers=headers)
        capabilities.raise_for_status()
        capability = next(
            item for item in capabilities.json()["capabilities"]
            if item["analysis_type"] == "punch_classification" and item["spec_version"] == 2
        )
        if not capability["executable"]:
            raise RuntimeError("punch_classification version 2 is not executable")
        metadata, contents = _package()
        response = client.post(
            "v1/measurement-sessions",
            headers=headers,
            data={"metadata": metadata.canonical_json()},
            files=[("files", (name, data, "text/csv")) for name, data in contents.items()],
        )
        response.raise_for_status()
        analysis = metadata.analyses[0]
        payload = None
        for _attempt in range(60):
            result = client.get(
                f"v1/measurement-sessions/{metadata.session_id}/analyses/{analysis.analysis_id}",
                headers=headers,
            )
            result.raise_for_status()
            payload = result.json()
            if payload["status"] not in {"pending", "processing"}:
                break
            time.sleep(0.25)
        if payload is None:
            raise RuntimeError("classification job did not return a status")
        if payload["status"] != "completed":
            raise RuntimeError(f"classification job did not complete: {payload}")
        model_result = payload["result"]
        if model_result["algorithm_version"] != "mitt_tcn_bilstm_lstm_v1":
            raise RuntimeError("unexpected punch-classification algorithm version")
        if model_result["total_punch_count"] != 0 or model_result["punches"] != []:
            raise RuntimeError("fixed no-punch fixture produced unexpected events")
        print(json.dumps({
            "status": "passed",
            "session_id": str(metadata.session_id),
            "algorithm_version": model_result["algorithm_version"],
        }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
