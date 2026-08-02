## Why

BoxingLens already provides IMU serial communication, protocol parsing, and CSV recording behavior, but `openspec/specs/` does not yet describe that behavior. Establishing a verified baseline now gives later changes an authoritative distinction between existing, modified, and new capabilities.

## What Changes

- Document the observable command-line behavior for discovering serial ports, reading device output, and sending configuration commands.
- Document the supported ANROT binary and NMEA parsing behavior, including incremental input handling and checksum rejection.
- Document the existing multi-port, gateway-grouped IMU CSV recording behavior and its current command options.
- Establish `pytest` as the shared framework for characterization tests that verify the documented baseline without intentionally changing runtime behavior.
- Establish a repository-wide OpenSpec policy requiring every current and future spec Scenario to be testable and to map to at least one identifiable automated, contract, or hardware-in-the-loop test case.
- Validate the artifacts strictly, execute the test suite, and perform completeness, correctness, and coherence verification before archive.
- Exclude punch analysis, force-plate integration, new recording formats, and fixes or enhancements to existing IMU behavior.

## Capabilities

### New Capabilities

- `imu-device-communication`: Existing command-line behavior for listing serial ports, displaying parsed device output, and sending a saved configuration command sequence.
- `imu-data-parsing`: Existing behavior for incrementally decoding supported ANROT binary frames and checksummed NMEA sentences into structured measurements.
- `imu-data-recording`: Existing behavior for recording parsed IMU gateway packets from one or more serial ports into gateway-specific CSV files.

### Modified Capabilities

None.

## Impact

- Adds baseline delta specifications under this change so they can become authoritative main specs when the change is archived.
- Adds `pytest` and `pytest-cov` development configuration and characterization coverage under `tests/` for the current command, parser, and recorder behavior.
- Adds repository-wide Scenario-to-test rules in `openspec/config.yaml`; this baseline change provides their first concrete application.
- Uses the current working-tree behavior of `anrot_imu_driver/commands/record_data.py`, including its user-modified 10-second default duration, as the baseline to preserve.
- Does not modify vendor material, public command behavior, parsing rules, or recording output in this change.
