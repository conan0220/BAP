## MODIFIED Requirements

### Requirement: Direct trajectory recording accepts either wrist

For `punch_trajectory` version 3, the Desktop App and Backend MUST accept a
left-wrist input, a right-wrist input, or both. At least one wrist MUST be
assigned. If both are assigned they MUST use different IMUs and CSV bindings.
The unassigned wrist MUST NOT produce a CSV, trajectories, or fabricated data.
Its punch count is zero in the existing Result schema, representing no measured
punches from that wrist. It does not assert that the unworn wrist did not move.

Single-wrist analysis MUST use that wrist's own initial heading. Paired analysis
MUST retain the existing shared-coordinate behavior and quality warnings. The
recording MUST start directly without a calibration phase. The existing v2
calibration contract and input requirements of other analyses are unchanged.

#### Scenario: Only the left wrist is worn
- **WHEN** one IMU is assigned to the left wrist and the right wrist is unassigned
- **THEN** direct recording and analysis can complete with only left trajectories

#### Scenario: Only the right wrist is worn
- **WHEN** one IMU is assigned to the right wrist and the left wrist is unassigned
- **THEN** direct recording and analysis can complete with only right trajectories

#### Scenario: Missing or duplicate assignment
- **WHEN** no wrist is assigned, or the same IMU is assigned to both wrists
- **THEN** the Desktop App does not enable measurement preparation
- **AND** Backend validation rejects empty or duplicate input bindings

#### Scenario: Older backend requires both wrists
- **WHEN** a single wrist is assigned but backend capability metadata still
  declares both wrist inputs mandatory
- **THEN** the Desktop App reports the backend update requirement before recording
