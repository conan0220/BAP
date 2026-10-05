## Why

Trajectory testing should work with one IMU worn on either wrist. Currently the
desktop assignment page, v3 input contract, and executor require both wrists.

## What Changes

- Allow either left, right, or both wrist inputs for direct trajectory recording.
- Keep at least one input mandatory and reject duplicate IMU/CSV assignments.
- Use the worn wrist's heading for a single-wrist recording. Preserve the shared
  heading and quality warnings for paired recordings.
- Keep the v3 Result schema and existing valid paired requests compatible.
- Keep other analyses and the older v2 calibration contract unchanged.
- Detect an older backend that still advertises both inputs as required before
  starting a single-wrist recording.
