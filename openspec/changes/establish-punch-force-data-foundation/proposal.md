## Why

Punch-force research requires trustworthy training data that pairs body-motion measurements with force-plate ground truth. The current recorder captures IMU samples, but it does not yet define a repeatable offline trial, preserve force-plate data alongside the IMU data, align the sources, or report whether a recording is suitable for research.

## What Changes

- Introduce trial-oriented offline recording for four nine-axis IMUs located on the right wrist, right arm, left arm, and force-plate contact surface.
- Record the force plate's original force-time signal as ground truth within the same trial.
- Preserve source data without destructive preprocessing and record the metadata needed to interpret and reproduce each trial.
- Align the IMU and force-plate sources onto a shared trial timeline while retaining source timestamps and alignment provenance.
- Assess recording completeness, timing integrity, missing or duplicate samples, and sensor saturation, and expose the resulting quality findings without silently repairing source data.
- Exclude punch-force prediction, application user interfaces, real-time analysis, and integration of punch-type or trajectory algorithms from this change.

## Capabilities

### New Capabilities

- `punch-force-trial-recording`: Capture and preserve one offline research trial containing four nine-axis IMU streams, force-plate ground truth, and the metadata needed to interpret the recording.
- `punch-force-time-alignment`: Produce a traceable common trial timeline for the independently timestamped IMU and force-plate measurements.
- `punch-force-data-quality`: Evaluate and report whether a recorded trial is complete and suitable for downstream punch-force research.

### Modified Capabilities

None.

## Impact

- Extends the IMU recording workflow under `anrot_imu_driver/` from gateway-oriented CSV output to trial-oriented research capture.
- Introduces an integration boundary for the punch force plate; the device protocol and connection details remain to be confirmed.
- Introduces a versioned trial manifest and quality/alignment outputs alongside raw recordings.
- Requires automated tests for recording structure, time alignment, source preservation, and quality reporting.
- Does not modify the vendor material under `ANROT-IMU-v1.3.6-windows-x64/`.
