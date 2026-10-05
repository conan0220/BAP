## Why

The current result view fits each punch independently, making different path
sizes appear similar. Users also need to select particular punches and inspect
them together. BAP_v2 and CodeData provide fixed-range and overlay references,
but do not provide arbitrary punch selection with stable session-wide bounds.

## What Changes

- Use one equal-axis cube computed from all trajectories in the current Result,
  including the origin and padding. Keep its center and range across selections.
- Retain the initial single-punch view and add overlay and side-by-side modes.
- Provide a checkable chronological punch table with hand, punch number,
  duration, path length, maximum displacement, and stable colors.
- Synchronize side-by-side camera manipulation and reset to common bounds.
- Keep current backend contracts, recording behavior, warnings, and Result data.
