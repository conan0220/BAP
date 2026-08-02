## Purpose

Define a repeatable offline research trial that preserves four nine-axis IMU streams, force-plate ground truth, and the context required to interpret the measurements later.

## ADDED Requirements

### Requirement: Complete punch-force trial capture
The system SHALL record a punch-force research trial as a single identifiable unit containing the force plate's original force-time measurements and exactly four IMU streams assigned to the right wrist, right arm, left arm, and force-plate contact surface.

#### Scenario: All expected sources complete a trial
- **WHEN** an operator records a trial while the four assigned IMUs and force plate are available
- **THEN** the system stores all five source streams under one trial identifier and reports the capture as complete

#### Scenario: An expected source is unavailable
- **WHEN** a trial ends without data from one or more expected sources
- **THEN** the system preserves any acquired source data but SHALL NOT report the trial as a complete capture

### Requirement: Canonical nine-axis IMU measurements
Each stored IMU sample SHALL expose source time, three-axis acceleration, three-axis angular velocity, and three-axis magnetic-field measurements with explicit units. Acceleration and angular-velocity fields SHALL remain independently accessible as the six-axis subset used by existing analysis workflows.

#### Scenario: Store a nine-axis sample
- **WHEN** the recorder receives a valid sample from an assigned IMU
- **THEN** the stored sample contains the source timestamp and all three axes for acceleration, angular velocity, and magnetic field with their units

#### Scenario: Read the six-axis subset
- **WHEN** a downstream analysis reads only acceleration and angular-velocity fields from a recorded IMU stream
- **THEN** it can obtain those six axes without requiring magnetic-field values as algorithm inputs

### Requirement: Raw source preservation
The system SHALL preserve received IMU and force-plate measurements and their source timestamps without overwriting them through filtering, interpolation, time alignment, unit conversion, or derived-metric calculation.

#### Scenario: Produce derived trial outputs
- **WHEN** the system aligns or validates a recorded trial
- **THEN** the original source measurements remain available unchanged alongside the derived outputs

### Requirement: Reproducible trial metadata
The system SHALL associate each trial with metadata that identifies the participant pseudonym, session and trial identifiers, sensor-to-placement assignments, device identifiers, sensor orientation descriptions, configured sampling settings, coordinate and unit conventions, recording start and end times, and data-schema and recorder versions.

#### Scenario: Inspect a recorded trial
- **WHEN** a researcher opens a completed or incomplete trial
- **THEN** the researcher can determine which device produced each stream, where and how it was mounted, how it was configured, and which schema and recorder versions produced the recording

### Requirement: Force-plate ground-truth preservation
The system SHALL store the force plate's original timestamped measurement channels together with their physical units and the calibration or conversion information supplied for the trial.

#### Scenario: Record force-plate measurements
- **WHEN** the force plate supplies measurements during a trial
- **THEN** the system preserves the original measurement sequence, timestamps, channel identities, units, and applicable calibration information under the trial identifier
