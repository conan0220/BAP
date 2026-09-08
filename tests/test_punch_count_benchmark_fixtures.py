from __future__ import annotations

from pathlib import Path

import pytest

from bap_common.analysis_session import SourceConnectionType
from bap_desktop.services.benchmark_recorder import load_benchmark_bundle


FIXTURE_DIRECTORY = Path(__file__).resolve().parent / "fixtures" / "punch_count"
EXPECTED_CASES = {
    "bap-punch-count-benchmark-20260908T055522Z-d7a88d4e.zip": (5, 5, 10),
    "bap-punch-count-benchmark-20260908T055600Z-362bf285.zip": (7, 7, 14),
    "bap-punch-count-benchmark-20260908T055654Z-4ef96ab6.zip": (11, 11, 22),
    "bap-punch-count-benchmark-20260908T055728Z-877a4a9c.zip": (10, 0, 10),
    "bap-punch-count-benchmark-20260908T055805Z-d7230646.zip": (0, 10, 10),
}


@pytest.mark.scenario("benchmark-data-recorder", "人工匯出的無線 IMU ZIP 通過 Benchmark loader")
@pytest.mark.parametrize("filename,expected_counts", EXPECTED_CASES.items())
def test_approved_wireless_benchmark_bundle(
    filename: str,
    expected_counts: tuple[int, int, int],
) -> None:
    bundle = load_benchmark_bundle(FIXTURE_DIRECTORY / filename)
    metadata = bundle.metadata

    assert (
        metadata.ground_truth.left_punch_count,
        metadata.ground_truth.right_punch_count,
        metadata.ground_truth.total_punch_count,
    ) == expected_counts
    assert set(bundle.csv_by_role) == {"left_wrist", "right_wrist"}
    assert {item.source.connection_type for item in metadata.inputs} == {
        SourceConnectionType.WIRELESS_RECEIVER
    }
    assert {item.source.port for item in metadata.inputs} == {"COM6"}
    assert {item.source.group_id for item in metadata.inputs} == {1}
    assert {item.source.node_id for item in metadata.inputs} == {0, 1}
    assert len({item.source.source_id for item in metadata.inputs}) == 2
    assert all(item.row_count > 0 for item in metadata.inputs)


def test_repository_contains_only_the_approved_benchmark_bundles() -> None:
    assert {path.name for path in FIXTURE_DIRECTORY.glob("*.zip")} == set(EXPECTED_CASES)
