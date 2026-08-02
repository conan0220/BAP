## Context

See `proposal.md` for motivation and scope. The repository currently provides a Python serial parser and a `record` command that writes gateway-oriented, fixed-width CSV rows for as many as 16 HI221 nodes. The compact `0x63` gateway frame supplies a shared millisecond timestamp and nine-axis measurements for each node. The current format does not describe a research trial, preserve force-plate data, retain alignment provenance, or produce a quality decision.

Four HI221 nodes can share one Dongle at up to the documented 200 Hz deployment tier; the force plate may use a different clock and sampling rate. Its connection protocol, timestamp semantics, channel layout, and calibration representation are not yet documented in the repository.

## Goals / Non-Goals

**Goals:**

- Keep capture, alignment, and validation independently repeatable.
- Preserve source evidence so parser, alignment, and quality logic can be revised without repeating an experiment.
- Make every derived timeline and quality decision traceable to a versioned method and configuration.
- Provide a stable nine-axis research representation whose acceleration and angular-velocity columns can also be consumed as a six-axis subset.
- Allow force-plate-specific communication to be added without coupling it to the trial format or quality rules.

**Non-Goals:**

- Define a punch-force prediction target or calculate labels such as peak force, impulse, or power.
- Filter, resample, segment, or featurize punch motion for model training.
- Generalize the first capture protocol beyond the four named IMU placements.
- Replace the existing gateway-oriented `record` command before the trial workflow is validated.

## Decisions

### 1. Store each trial as a versioned, self-contained bundle

A trial bundle will be the unit of capture, processing, validation, transfer, and recovery. It will contain:

```text
<trial-id>/
  manifest.json
  source/
    <verbatim IMU transport capture>
    <verbatim force-plate capture or lossless received samples>
  measurements/
    imu.csv
    force-plate.csv
  derived/
    alignment.json
  reports/
    quality.json
```

`manifest.json` will carry the schema version, capture state, participant pseudonym, session and trial identifiers, source inventory, sensor placement and orientation descriptions, device and capture configuration, units and coordinate conventions, recorder version, and file checksums. The canonical IMU table will use one row per node sample with explicit acceleration, angular-velocity, and magnetic-field columns rather than repeating a fixed set of 16 wide node groups.

Capture will occur in a staging bundle. Normal completion finalizes the manifest and checksums. Interrupted or partial capture remains inspectable but is finalized with an incomplete state rather than discarded or represented as successful.

**Alternatives considered:** Continuing with one wide CSV was rejected because it loses trial context, produces unused columns, and couples consumers to a maximum node count. A database-first design was rejected because portable, inspectable research trials are more useful at this stage and do not require a running service. Parquet can be added later as a derived research export if scale requires it.

### 2. Separate source adapters from the trial coordinator

A trial coordinator will own trial lifecycle, metadata, host timing, and output finalization. IMU and force-plate adapters will expose timestamped sample batches and source metadata through the same conceptual boundary while retaining device-specific payloads and diagnostics.

The HI221 adapter will reuse the existing `0x63` parser but add lossless source capture and long-form canonical output. The force-plate adapter will be implemented after its protocol is confirmed. If the force plate supplies an exported file rather than a live stream, the adapter may import that file into the same trial lifecycle as long as identity and timing can be verified.

**Alternatives considered:** Adding force-plate parsing directly to the current IMU recording loop was rejected because it would couple two independent devices and make protocol changes affect trial storage and validation.

### 3. Record three layers of time evidence

Where available, every sample or batch will retain:

1. the device or gateway source timestamp;
2. a host monotonic receive timestamp captured by the coordinator;
3. a derived shared-trial timestamp produced by offline alignment.

Nodes from one HI221 gateway share its `gw_ts_ms` clock mapping. Other gateways and the force plate receive separate mappings. Alignment will initially model a clock as an offset when only one reliable anchor exists and as an affine mapping when multiple anchors provide evidence of drift.

Hardware synchronization markers, if the force plate exposes them, are preferred. Otherwise, the impact event measured by the contact-surface IMU and the force-time signal will provide offline alignment anchors. The alignment artifact will store the selected method, parameters, anchors, residual diagnostics, acceptance thresholds, and method version.

Alignment assigns mapped timestamps but does not resample or overwrite measurement streams. A later analysis can select an interpolation strategy without changing the trial evidence.

**Alternatives considered:** Host arrival time alone was rejected because serial and operating-system latency can vary. Replacing source timestamps with aligned timestamps was rejected because it prevents auditing and improved realignment. Mandatory hardware synchronization was not selected because force-plate support is not yet known.

### 4. Treat the force-time signal as ground-truth evidence, not a finalized prediction label

This change will preserve the force plate's original channels, units, timestamps, and calibration evidence. Definitions of peak force, impulse, contact duration, and any composite power score will be introduced in a later algorithm-focused change after the measurement protocol is confirmed.

**Alternatives considered:** Computing a single force label during capture was rejected because it would prematurely embed an unsettled scientific definition and could force experiments to be repeated.

### 5. Run deterministic quality validation after capture and alignment

Validation will be a separate offline operation over a finalized or incomplete trial bundle. Rules and thresholds will be versioned configuration recorded in `quality.json`. Findings will identify their source, channel, time interval or sample count, severity, and evidence. The aggregate disposition will be `pass`, `warning`, or `fail`.

The first rule set will cover source inventory, assignment, empty and prematurely terminated streams, timestamp regression and duplication, observed sample rate and gaps, missing or invalid values, configured-range saturation, and alignment acceptance. Validation will never edit the source layer. If a later cleanup operation creates a derivative, its transformation provenance must be recorded separately.

**Alternatives considered:** Repairing duplicates and gaps during capture was rejected because it conceals recorder and device behavior and prevents alternative cleanup policies from being evaluated.

### 6. Keep research identity pseudonymous

Trial metadata will require a participant pseudonym rather than a person's name or contact information. Any identity mapping remains outside the trial bundle and outside this change.

**Alternatives considered:** Storing personal identity in the manifest was rejected because it is unnecessary for the technical dataset and increases privacy risk.

## Risks / Trade-offs

- **[Four-node HI221 deployments are limited to the documented 200 Hz tier]** → Run a pilot before large-scale collection, record configured and observed rates, and treat sufficiency for force prediction as a later empirical decision.
- **[Impact dynamics may saturate an IMU or occur faster than its usable bandwidth]** → Record configured ranges, detect saturation, and reject unsuitable trials rather than inferring clipped peaks.
- **[Software alignment may not reach the precision needed for force research]** → Preserve all clock evidence, report residual error, support hardware markers through the adapter boundary, and fail trials that do not meet configured acceptance criteria.
- **[Magnetic disturbance near the force plate may degrade magnetometer data]** → Preserve nine-axis measurements and report range or integrity findings; do not make accepted capture depend on magnetometer-derived orientation in this change.
- **[The force-plate protocol may not expose source timestamps or original raw payloads]** → Preserve the most lossless representation available, capture host monotonic timing, and document the limitation in source and alignment metadata.
- **[Portable CSV and JSON artifacts use more storage than compact binary formats]** → Preserve research transparency first; add a derived columnar export only after data volume justifies it.

## Migration Plan

1. Confirm and document the initial four-IMU hardware profile and force-plate interface.
2. Add the trial bundle schema, source-adapter boundary, and deterministic fixture data without changing the existing `record` behavior.
3. Add the HI221 trial adapter and force-plate adapter, then validate them independently.
4. Add offline alignment and quality reporting over captured fixtures.
5. Run pilot captures and refine versioned acceptance thresholds before treating trials as research-ready.
6. Retain the existing recorder as the rollback path until the trial workflow passes automated and hardware-in-the-loop verification.

## Open Questions

- What force-plate model, connection protocol, channel layout, timestamp resolution, sampling rate, measurement range, and calibration format are available?
- Do the force plate or acquisition hardware expose a trigger, synchronization pulse, or clock signal that can be recorded with the IMU data?
- What exact anatomical locations do `right arm` and `left arm` mean, and how will mounting orientation be reproduced between sessions?
- Which initial HI221 output rate, acceleration range, angular-velocity range, and alignment acceptance thresholds should the pilot use?
