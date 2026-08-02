## Purpose

Define transparent and reproducible quality checks that show whether a recorded punch-force trial is complete and suitable for downstream force-analysis research.

## ADDED Requirements

### Requirement: Required-source completeness checks
The system SHALL verify that a trial contains the force-plate stream and all four assigned IMU streams, and SHALL report missing, empty, prematurely terminated, or unassigned sources.

#### Scenario: Trial is missing an IMU stream
- **WHEN** a recorded trial contains fewer than four assigned IMU streams
- **THEN** the quality report identifies the missing placement and gives the trial a failing disposition

### Requirement: Per-source measurement integrity checks
The system SHALL evaluate each source for timestamp regressions, duplicate timestamps, sampling gaps, observed sampling rate, missing or invalid measurement fields, and values at or beyond the configured sensor range.

#### Scenario: IMU timestamps are duplicated
- **WHEN** an IMU stream contains repeated source timestamps
- **THEN** the quality report identifies the affected source and reports the count or intervals of duplicated timestamps

#### Scenario: Sensor measurements reach the configured range
- **WHEN** an IMU or force-plate measurement reaches or exceeds its configured valid range
- **THEN** the quality report identifies the source, channel, affected interval, and possible saturation

### Requirement: Traceable quality report
The system SHALL produce a machine-readable quality report containing a trial disposition of `pass`, `warning`, or `fail`, individual findings with severity and affected source or interval, the applied thresholds, and the quality-check version.

#### Scenario: Review trial quality
- **WHEN** quality validation completes for a trial
- **THEN** the report explains the trial disposition through its individual findings and records the thresholds and checker version used

### Requirement: Quality validation does not conceal source defects
The system SHALL NOT modify raw source data to remove or conceal defects discovered during quality validation. Any cleaned or corrected derivative SHALL remain distinguishable from the raw data and SHALL record the transformation applied.

#### Scenario: A derivative removes duplicate samples
- **WHEN** a downstream processing step creates a derivative with duplicate samples removed
- **THEN** the raw samples remain unchanged and the derivative identifies the transformation and affected samples

### Requirement: Alignment quality contributes to trial disposition
The system SHALL include time-alignment success and diagnostics when determining whether a trial is suitable for alignment-dependent punch-force research.

#### Scenario: Alignment fails acceptance criteria
- **WHEN** any required source is marked alignment-failed
- **THEN** the quality report gives the trial a failing disposition for alignment-dependent use and references the alignment diagnostics
