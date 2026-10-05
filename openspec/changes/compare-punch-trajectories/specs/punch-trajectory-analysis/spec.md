## ADDED Requirements

### Requirement: Trajectory views share one Result-wide scale

The Desktop App MUST use the same equal-axis coordinate limits and center for
every punch in a Result, including single, overlay, and side-by-side views.
Default limits MUST contain all Result points and the origin. Selecting a subset
MUST NOT refit the bounds. Camera reset MUST restore these common bounds.

#### Scenario: Compare punches with different extents
- **WHEN** the user switches between small and large or opposite-direction punches
- **THEN** the coordinate limits remain unchanged and contain all their points
- **AND** each axis uses the same physical scale

### Requirement: Users select individual punches for comparison

The Desktop App MUST allow the user to check any subset of punches across both
hands and display it as an overlay or separate equal-scale plots. Each punch
MUST retain its color across selection changes. Mode changes MUST preserve
comparison selections. The interface MUST retain per-punch numerical metrics
when the 3D renderer cannot be initialized. Changing the view MUST NOT mutate
the Result or run backend analysis again.

#### Scenario: Compare a selected subset across hands
- **WHEN** the user checks individual punches and switches comparison modes
- **THEN** only checked punches are plotted and the checked subset is preserved

#### Scenario: Clear comparison selection
- **WHEN** the user clears all checked punches
- **THEN** no old trajectory remains plotted and an empty selection is reported

#### Scenario: Manipulate side-by-side plots
- **WHEN** the user finishes rotating or zooming a plot, or selects a camera preset
- **THEN** every compared plot uses the same camera orientation and axis limits

#### Scenario: Compare without a renderer
- **WHEN** 3D renderer initialization fails
- **THEN** the user can still select punches and read their individual metrics
