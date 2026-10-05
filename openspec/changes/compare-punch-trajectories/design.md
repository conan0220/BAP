## Reference Comparison

- BAP fits the selected punch on each selection and supports only one trajectory.
- BAP_v2 adds an optional fixed cube side length and an all-punch overlay. Its
  fixed range is initially disabled and its center still follows the selection.
  Its backend also differs in single-IMU support and calibration handling;
  those changes are outside this presentation change.
- CodeData/webview/viewer.html uses cubic ranges and colored overlays through
  Plotly. BAP keeps its existing embedded Matplotlib renderer and dependencies.

## Decisions

Compute bounds from every point in the Result, not only selected punches or the
largest individual punch. Use the largest combined axis span with 20% padding,
and a minimum 0.1 m cube for stationary points. The origin and bounds stay in
the same position when switching selections. All views use orthographic
projection, equal axis aspect, and the same limits. Scale is shared within a
Result; separate measurement sessions compute their own common bounds.

Preserve the earliest-punch initial view. Comparison selections are independent
of the single-punch selectors and persist when switching display modes. A
scrollable checkable table contains both hands and per-punch metrics, with
select-all and clear actions. Colors and line styles are assigned once in
chronological order. Endpoints use same-color triangles; origins use green dots.

Side-by-side mode uses a two-column grid in a scrollable canvas. Presets apply
to every subplot. Mouse release copies rotation and axis limits to the other
subplots. Reset restores the common Result bounds and selected preset. An empty
comparison clears all curves and displays an explicit empty selection summary.
Renderer initialization failure retains the selection table and numeric metrics.

## Verification

Focused Qt tests exercise subset selection across hands, mode transitions,
stable bounds and colors, opposite-direction paths, stationary points, empty
selection, shared camera state, immutable Result data, and renderer fallback.
Existing desktop page tests verify integration with the result workflow.
