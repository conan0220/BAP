## Context

See `proposal.md` for motivation. The implemented IMU surface spans the command-line entry point, serial-port commands, ANROT binary and NMEA parsers, and the gateway-grouped CSV recorder. The repository currently has no automated tests and no main OpenSpec requirements. Stable HI221 facts and setup procedures exist under `docs/`, but those documents are evidence and guidance rather than product requirements.

The working tree contains a user change that makes the recording duration default to 10 seconds. This baseline must preserve that change and must not silently substitute the committed branch's indefinite default.

## Goals / Non-Goals

**Goals:**

- Establish the smallest set of capability boundaries that accurately describes the existing public IMU behavior.
- Add deterministic characterization tests for behavior that can be verified without attached hardware.
- Make every OpenSpec scenario traceable to at least one identifiable test case.
- Apply structural, executable, and change-level verification before the baseline is archived.
- Make later proposals identify additions and modifications against an explicit baseline.
- Keep any mismatch between implementation, documentation, and proposed requirements visible.

**Non-Goals:**

- Refactor command or parser internals while adding coverage.
- Turn accidental implementation defects into desired long-term behavior when no user-visible contract depends on them.
- Verify electrical, wireless, timing, or throughput behavior that requires attached hardware.
- Establish a global coverage-percentage gate before representative baseline tests exist.
- Introduce property-based testing in this change.
- Baseline punch-type recognition or punch-trajectory analysis whose implementations are not present in the tracked repository.

## Decisions

### 1. Separate the baseline into three user-observable capabilities

The baseline uses `imu-device-communication`, `imu-data-parsing`, and `imu-data-recording`. These boundaries follow what operators and downstream code can observe rather than mirroring every Python module.

- Communication covers discovery, live monitoring, and the saved device-command sequence.
- Parsing covers incremental binary and NMEA decoding independently of serial hardware.
- Recording covers the multi-port command and its gateway-specific CSV artifacts.

**Alternatives considered:** A single `imu-driver` capability was rejected because later force-data work can modify recording without changing command sending or protocol parsing. Separate capabilities for every command and frame type were rejected as too granular for the current system.

### 2. Treat verified working-tree behavior as the baseline

Requirements are derived from the current source and executable examples, with vendor references used only to interpret data formats. The uncommitted 10-second recording default is explicitly included because repository guidance requires preserving the user's current change.

If characterization reveals that a proposed requirement does not match executable behavior, this baseline change will correct the requirement or narrow its scenario. It will not change runtime behavior to make an aspirational requirement pass. A defect that should be fixed will receive a separate follow-up change.

**Alternatives considered:** Using README text as authoritative was rejected because it omits the recording command and may diverge from code. Using only committed `HEAD` was rejected because it would discard the active user change.

### 3. Use pytest for deterministic characterization at hardware boundaries

`pytest` is the common test runner. Tests use pytest fixtures, parametrization, `tmp_path`, and `monkeypatch`, with `unittest.mock` where explicit fakes are clearer. Fixed ANROT frames, checksummed NMEA sentences, fake serial ports, controlled clocks, and temporary output directories isolate the tests from attached hardware.

Test discovery and markers are configured in `pyproject.toml`. At minimum, `hardware`, `slow`, and `dataset` markers distinguish tests that are unsuitable for the fast default suite. The baseline suite remains non-hardware; future hardware-in-the-loop tests must be explicitly marked. `pytest-cov` reports branch coverage as a diagnostic, but this change does not introduce an arbitrary global percentage threshold. Property-based testing can be proposed later if example-based protocol fixtures reveal insufficient input coverage.

Tests target observable results: command output and exit behavior, command bytes and ordering, emitted structured measurements, file naming, CSV headers and rows, duration handling, and cleanup. Internal helper layout is not part of the baseline.

**Alternatives considered:** Hardware-only verification was rejected because it would be slow, non-deterministic, and unavailable in continuous integration. The standard-library `unittest` runner was rejected because pytest provides concise fixture, parametrization, temporary-path, and marker support for the planned test matrix. Snapshotting whole console sessions was rejected because inconsequential formatting changes would create brittle tests.

### 4. Preserve repository-wide scenario-to-test traceability

`openspec/config.yaml` defines the repository-wide policy: every current and future Scenario must be testable, must map to a test task, and must have test evidence before archive. This baseline change is the first application of that policy; every `#### Scenario` in its three delta specs maps to at least one test case.

The exact capability and Scenario names are recorded in the test identifier, docstring, marker metadata, or a maintained traceability audit. A parametrized test may cover multiple examples, but each Scenario must remain individually identifiable in pytest output. One test may support multiple Scenarios only when the audit lists every mapping explicitly.

Scenario coverage is the primary completeness measure; line and branch coverage are supporting diagnostics. A final audit compares all scenario headings with collected pytest cases and treats any unmapped scenario as incomplete work.

**Alternatives considered:** Relying only on code coverage was rejected because executing a line does not prove a requirement scenario. Requiring one test function per scenario was rejected because parametrization can express protocol variants more clearly while retaining distinct test cases.

### 5. Verify the baseline in three layers

Before archive, the change is checked at three different layers:

1. `openspec validate baseline-existing-imu-data-capabilities --type change --strict` validates artifact structure and requirement syntax.
2. The focused and complete pytest suites validate executable behavior, with branch coverage reported for review.
3. OpenSpec change verification checks completeness, correctness, and coherence, including whether every scenario has corresponding test evidence. Use the official verification workflow when available; otherwise perform and record an equivalent review because the current core profile does not install a verification skill.

OpenSpec verification is evidence review rather than a substitute for executing pytest. Any uncovered scenario prevents this project from treating the change as archive-ready even if the tooling reports only a warning.

**Alternatives considered:** Treating strict validation as sufficient was rejected because it cannot establish runtime correctness. Treating automated test success as sufficient was rejected because it does not by itself detect missing scenario coverage or inconsistency among planning artifacts.

### 6. Do not conceal known gaps through baseline wording

The specs describe supported behavior without claiming that malformed input is diagnosed comprehensively, timestamps are synchronized across gateways, CSV output is research-ready, or the recorder validates data quality. Those are not existing capabilities and belong to later changes.

**Alternatives considered:** Describing desired robustness in the baseline was rejected because main specs would then claim behavior the system does not provide.

## Risks / Trade-offs

- **[Characterization can freeze incidental behavior]** → Specify stable inputs, outputs, and error boundaries while avoiding private structure and inconsequential formatting.
- **[Mocks can differ from physical serial devices]** → Keep protocol fixtures byte-accurate and record hardware verification as a separate future activity rather than overstating coverage.
- **[OpenSpec verification may warn without blocking archive]** → Make zero uncovered scenarios an explicit project archive condition and keep pytest execution separate.
- **[Coverage metrics can reward low-value tests]** → Review scenario coverage first and use branch coverage only to find unexamined paths.
- **[Existing examples contain presentation defects]** → Test decoded values and required output fields, not unrelated labels or formatting mistakes; propose fixes separately.
- **[The user-modified duration default may change before implementation]** → Re-read the working tree before applying this change and reconcile the baseline explicitly if the user has changed it again.

## Migration Plan

1. Add and configure the pytest development dependencies, markers, fixtures, and scenario-traceability convention.
2. Add characterization tests for the three capability specs without editing runtime modules.
3. Run the focused and complete suites with branch-coverage reporting and compare every failure with the current working-tree behavior.
4. Narrow or correct baseline requirements when they overstate current behavior; record desired fixes as separate changes.
5. Run strict OpenSpec validation and the completeness, correctness, and coherence verification review; resolve every uncovered scenario.
6. Archive the completed change so its three delta specs become authoritative main specs.

There is no runtime deployment or rollback. If the baseline is abandoned before archive, remove only its change artifacts and newly added characterization-test configuration and files; existing runtime behavior remains unchanged.
