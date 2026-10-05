## Implementation

- [x] Compare the BAP, BAP_v2, and CodeData trajectory renderers.
- [x] Apply common Result-wide cubic bounds with a stable center.
- [x] Add arbitrary cross-hand punch selection, select-all, and clear actions.
- [x] Implement overlay and scrollable side-by-side comparison modes.
- [x] Preserve punch colors, selection state, warnings, and per-punch metrics.
- [x] Synchronize subplot cameras and restore common bounds on reset.
- [x] Verify selection, scale, rendering fallback, and existing page integration.

## Verification

- `python -m pytest tests/desktop tests/backend/test_punch_trajectory.py -q`:
  222 passed; three existing FastAPI/Starlette deprecation warnings.
- After final tick density, camera elevation, and layout adjustments:
  `python -m pytest tests/desktop/test_trajectory_view.py -q`: 13 passed.
- Rendered the existing CodeData jab1, hook6, and upper JSON samples in all
  three modes at 1000 and 640 logical-pixel widths. Inspected native Qt
  screenshots and the complete scrollable grid for visible paths and labels.
- This change does not require a live backend to render a validated Result.
  No live IMU recording or deployed-backend end-to-end run was performed.
