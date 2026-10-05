## Implementation

- [x] Permit either wrist in trajectory assignment and session preparation.
- [x] Keep empty selections and duplicate IMU assignments blocked.
- [x] Relax v3 wrist roles while enforcing at least one input and unique CSVs.
- [x] Analyze only present wrists using the appropriate reference heading.
- [x] Preserve paired processing, v2 calibration, and other analysis contracts.
- [x] Detect older backend role requirements before single-wrist recording.
- [x] Test single-left, single-right, paired recording, and HTTP persistence.

## Verification

`python -m pytest tests/desktop tests/backend/test_punch_trajectory.py
tests/backend/test_analysis_sessions_api.py tests/backend/test_analysis_registry.py
tests/test_analysis_contracts.py -q --disable-warnings`

Result: 292 passed. Existing dependency and datetime deprecation warnings remain.
`git diff --check` passed. No physical IMU or deployed-backend run was performed.

Both desktop and backend must run the updated code. Only updating the desktop
cannot make an older backend accept a missing wrist input.
