# AutoForm live rate-matrix contract

AutoForm's existing `rate_matrix` section is a scientific editor, not a table of
independent display values. Its plain configuration declares a `target` dotted
attribute path and optional `size_attr`; the scientific model owns the matrix,
state count, fitting parameters and links. `RateMatrixBinding` in
`chisurf/core/dataspec/rate_binding.py` supplies toolkit-neutral live reads,
addressed-cell commits, parameter lookup and owner-scoped change notification.
The binding is a runtime handle and is **not** a project-state record.

## Editing and scientific identity

- A cell edit reads the current scientific vector, replaces the addressed
  source→target entry and writes through its declared model property. Never
  reconstruct the vector from displayed spin-box values: another parameter or
  dependency may have changed since the last refresh, and display rounding or
  clamping is not a scientific edit.
- Reject a non-finite value, an out-of-range address or a mismatched matrix size
  before writing. Scientific constraints remain the model's responsibility.
- Resolve the actual fitting parameter from the declared rate group. Keep its
  existing object, UID, bounds, fixed flag and link; do not manufacture a
  display-only parameter or persist a Qt controller.
- Notify the addressed model/fit, not whichever fit is globally selected. After
  a commit or detail action, reload values and metadata with signals blocked so
  repainting does not create additional edits.

In the Qt AutoForm renderer, checked means fixed and unchecked means free. A
linked parameter uses the partial state and retains the shared parameter-detail
controller. Its blue/link display is refreshed from the live parameter, just as
its value is. A value outside the display range remains scientific state until
that particular cell is edited; rendering another cell is not permission to
clamp it.

## Larger matrices and constrained windows

Columns retain the minimum width needed by their embedded controls. A narrow
viewport uses horizontal scrolling instead of squeezing values, checkboxes or
step controls into overlapping cells. Row-height calculation accounts for the
actual header and scrollbar chrome. A six-state constrained-view regression
scrolls to and checks the complete final row/column control.

## Persistence and verification

Use the shared canonical scientific project snapshot and ordinary `.cs.pto`
save/load path. Neither a widget nor a binding, controller, Qt item/index,
connection or callback belongs in the archive. A later renderer can consume the
same model state, plain declaration and binding semantics.

Focused tests:

- `test/core/test_rate_matrix_binding.py`: live-value preservation, real nested
  parameter identity, addressed-owner notification, rejected edits, and an
  ordinary fresh interpreter with all Qt imports blocked.
- `test/gui/test_rate_matrix_live_binding.py`: externally changed and linked
  rates, fixed/free controls, detail refresh, constrained six-state access, and
  real keyboard editing of measured FCS kinetics. The scientific case verifies
  changed prediction/relaxation modes, exact canonical recapture and a fresh
  interpreter that blocks optional MMFDB and original input-file access.
- `test/gui/test_rate_matrix.py`: existing section behavior and resizing.

Set `CHISURF_RATE_CAPTURE_DIR` to a dedicated evidence directory to capture
matching 620×900 and 360×600 views. Compare retained pre-change images with the
same state and scroll position; a screenshot of the rightmost column separately
proves scrolling access, not pixel parity with the initial leftmost view.

This shared-editor enhancement is not acceptance of all configured models,
actual Main publication, complete history or authenticated backend lifecycles.
Those retain their separate catalogue/application gates.
