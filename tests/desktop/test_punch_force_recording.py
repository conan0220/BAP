from pathlib import Path
from uuid import uuid4

import pytest

from bap_desktop.services.analysis_recording import LiveAnalysisRecording, source_id
from bap_desktop.services.imu_discovery import ImuSource
from bap_desktop.services.imu_scan import ConnectionType


@pytest.mark.scenario("punch-force-analysis", "校正完成後準備打擊")
def test_force_recording_keeps_physical_parameters_and_separate_time_boundaries(tmp_path: Path):
    class Clock:
        value = 10.0
        def __call__(self):
            return self.value
    class Capture:
        def __init__(self, root, *, assignments, monotonic, **_kwargs):
            self.sources = tuple(assignments.values())
            self.session_id = uuid4()
            self.directory = Path(root) / str(self.session_id)
            self.csv_ids = {source_id(source): uuid4() for source in self.sources}
            self.started_monotonic = monotonic()
        def start(self):
            self.directory.mkdir(parents=True)
        def discard(self):
            pass
        def interrupted_sources(self, *, now=None):
            return ()
    clock = Clock()
    recording = LiveAnalysisRecording(
        tmp_path,
        assignments={
            "bag_top": ImuSource("COM6", ConnectionType.WIRELESS_RECEIVER, 0, 0),
            "bag_bottom": ImuSource("COM6", ConnectionType.WIRELESS_RECEIVER, 0, 1),
        },
        analysis_type="punch_force", spec_version=1, desktop_version="0.1.22",
        analysis_parameters={
            "bag_mass_kg": 36.0, "bag_length_m": 1.24,
            "bag_diameter_m": 0.335, "sensor_distance_m": 1.24,
        },
        monotonic=clock, capture_factory=Capture,
    )
    recording.start()
    clock.value = 12.0
    assert recording.complete_calibration() == 2_000_000
    clock.value = 15.0
    assert recording.begin_measurement() == 5_000_000
    assert recording.job.parameters == {
        "bag_mass_kg": 36.0, "bag_length_m": 1.24,
        "bag_diameter_m": 0.335, "sensor_distance_m": 1.24,
        "calibration_end_elapsed_us": 2_000_000,
        "measurement_start_elapsed_us": 5_000_000,
    }
    recording.abort()
