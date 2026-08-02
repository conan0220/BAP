## Purpose

Define how independently timestamped IMU and force-plate streams receive a traceable common trial timeline for offline comparison without losing their original timing evidence.

## ADDED Requirements

### Requirement: Shared trial timeline
The system SHALL provide a time mapping from every recorded IMU and force-plate source clock to a shared trial timeline while retaining each original source timestamp.

#### Scenario: Align a complete trial
- **WHEN** the system successfully aligns a trial containing all expected sources
- **THEN** every stored measurement can be located on the shared trial timeline and its original source timestamp remains available

### Requirement: Alignment provenance
The system SHALL record the alignment method, method version, input anchors or timing evidence, estimated clock mapping or offset, configuration parameters, and alignment quality measurements used for each source.

#### Scenario: Inspect how a source was aligned
- **WHEN** a researcher reviews an aligned source stream
- **THEN** the researcher can identify how the alignment was produced and which evidence and parameters supported it

### Requirement: Deterministic offline alignment
The system SHALL produce the same aligned timeline when the same raw trial, alignment method version, and configuration are processed again.

#### Scenario: Repeat an alignment
- **WHEN** the same raw trial is aligned twice using the same method version and configuration
- **THEN** the resulting time mappings and reported alignment measurements are identical

### Requirement: Explicit alignment failure
The system SHALL mark a source or trial as alignment-failed when the available timing evidence cannot satisfy the configured alignment acceptance criteria, and SHALL NOT silently present an estimated mapping as accepted.

#### Scenario: Timing evidence is insufficient
- **WHEN** a source lacks enough timing evidence to meet the configured acceptance criteria
- **THEN** the system preserves the source data, reports the alignment failure and supporting diagnostics, and excludes the trial from alignment-dependent use by default
