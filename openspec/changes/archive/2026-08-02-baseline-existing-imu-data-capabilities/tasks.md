## 1. Characterization Test Foundation

- [x] 1.1 Add `pytest` and `pytest-cov` as development dependencies and configure test discovery, strict configuration, and the `hardware`, `slow`, and `dataset` markers in `pyproject.toml`.
- [x] 1.2 Add shared byte-accurate ANROT frame fixtures and checksummed NMEA fixtures under `tests/` without modifying runtime modules.
- [x] 1.3 Add reusable fake serial-port, controlled-clock, temporary-output, and CLI invocation helpers.
- [x] 1.4 Apply the repository-wide traceability policy to this baseline by recording the exact capability and Scenario name for every test case and keeping parametrized Scenario cases individually identifiable in pytest output.

## 2. IMU Data Parsing Baseline

- [x] 2.1 Add individually traceable pytest cases for binary input split across chunks, leading noise, invalid CRC, and recovery for later valid input.
- [x] 2.2 Add individually traceable pytest cases for supported single-device `0x91`, `0x92`, and `0x81` payload fields and format-specific scaling.
- [x] 2.3 Add individually traceable pytest cases for complete `0x63` gateway packets, the 16-node limit, and incomplete final node blocks, including metadata, nine-axis scaling, shared timestamps, and node ordering assertions.
- [x] 2.4 Add individually traceable pytest cases for supported valid NMEA sentences, incomplete NMEA input, invalid checksums, unsupported sentence types, and continued parsing.

## 3. IMU Device Communication Baseline

- [x] 3.1 Add individually traceable pytest cases for populated and empty operating-system port inventories.
- [x] 3.2 Add individually traceable pytest cases for live monitoring of mixed valid input, invalid baud rates, serial-access failures, frame-rate display, and interruption cleanup.
- [x] 3.3 Add individually traceable pytest cases for successful saved-command transmission, output-stop retry exhaustion, later-command failure, and invalid send baud rates, including 8-N-1 configuration, CRLF termination, ordering, acknowledgements, and displayed responses.

## 4. IMU Data Recording Baseline

- [x] 4.1 Add individually traceable pytest cases for valid recording options, missing ports, invalid baud rates, invalid durations, output defaults, and the current 10-second duration default.
- [x] 4.2 Add an individually traceable pytest case proving that interleaved input from multiple serial ports retains isolated incremental parser state.
- [x] 4.3 Add individually traceable pytest cases for two gateway identifiers, lazy file creation when no gateway packet is received, output naming, separate files, and the `unknown` gateway suffix.
- [x] 4.4 Add individually traceable pytest cases for gateway CSV rows, absent node slots, available and unavailable numeric precision, the two timing columns, 16 node groups, and packet-position mapping.
- [x] 4.5 Add individually traceable pytest cases for configured-duration completion, keyboard interruption, serial-access failure, periodic flushing, and resource cleanup.

## 5. Baseline Verification

- [x] 5.1 Audit every `#### Scenario` heading in the three delta specs against collected pytest cases and resolve every missing or ambiguous mapping.
- [x] 5.2 Run the focused characterization tests and then the complete default pytest suite with branch-coverage reporting; confirm that hardware-marked tests are not required by the default suite.
- [x] 5.3 Confirm that no runtime source file was changed by this baseline work and reconcile failures by narrowing inaccurate baseline requirements or recording desired runtime fixes as separate OpenSpec changes.
- [x] 5.4 Run `openspec validate baseline-existing-imu-data-capabilities --type change --strict` and resolve every validation error.
- [x] 5.5 Perform the OpenSpec completeness, correctness, and coherence verification workflow, using the official verifier when available or an equivalent recorded review, and confirm that no Scenario is uncovered before archive.
