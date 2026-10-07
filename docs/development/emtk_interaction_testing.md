---
type: Development Note
title: Native UI interaction and headless checks
description: Keyboard navigation, persisted window geometry, and the shared emtk Driver used to verify ChiSurf controls.
tags: [development, gui, testing]
audience: developer
---

# Native UI interaction and headless checks

Native emtk forms support Tab and Shift-Tab within the current window. Enter
and Space activate a focused button or toggle. Left and Right adjust sliders;
Up and Down change a focused combo. Tab into a text field to edit its contents.
The focused control has a visible outline. Games accept Shift and keypad arrow
keys; Control, Alt and Meta remain application shortcuts.

![A form with a focused control](../guides/figures/emtk_keyboard_focus.png)

Standalone plugin windows restore size, position and dock layout. A position
outside the primary screen is discarded. Qt hosts report moves; native GLFW
hosts restore position when supported. Offscreen hosts have no desktop position.
Viewport-derived panel regions continue following the host size.

The documentation browser inherits the application font and font size. Reset
zoom returns to that configured size. Code blocks retain their code font.

![Documentation using the application font](../guides/figures/emtk_help_font.png)

Use `emtk.testing.Driver` to drive real input into an app without opening a
window. It records screenshot font metrics, locates named controls or captions,
and delivers pointer press/release and keyboard events:

```python
from emtk.keys import KEY_TAB, KEY_RETURN
from emtk.testing import Driver

# app is an existing plugin factory result; disable persistence for test runs.
driver = Driver(app, (1100, 720))
driver.frame(2)
print(driver.ids())
driver.click("run")
driver.settle(timeout=30)
driver.press(KEY_TAB)
driver.press(KEY_RETURN)
driver.screenshot("renders/checked.png")
app.close()
```

Unknown targets raise `LookupError`; unfinished workers raise `TimeoutError`.
The driver does not close the app. Tables and node editors consume handled
wheel events once; idle redraws must leave their scroll or zoom unchanged.

Run targeted files through the project test environment:

```sh
QT_QPA_PLATFORM=offscreen CHISURF_SETTINGS_DIR=/tmp/chisurf-ui-check \
PYTHONPATH="/Users/tpeulen/dev/emtk:modules/chimol:modules/mmfdb/src:." \
pixi run -e test python -m pytest test/gui/test_autoform_state.py -q
```

Adapt the emtk checkout path to your machine. Build compiled providers with
`pixi run -e test build-extensions` first. Sibling builds use their target
prefix for both tools and HDF5 validation; they must not inherit pixi's
`CONDA_PREFIX`. For migration review, capture the old control first, keep a
before/after inventory, and inspect both PNGs. Tests that only construct a
widget cannot establish layout or control parity.

A recorded target without a rectangle is currently unavailable, for example an
image canvas before data loads. Driver excludes it from `ids()` and raises
`LookupError` rather than inventing a click location. Composite hosts forward
optional key-release hooks only when a child implements them. Form callbacks
receive the committed field value.


## Isolated plugin interaction gate

`test/e2e/test_click_all_plugins.py` discovers native entrypoints and the
remaining Qt-only factories. Each plugin runs in its own process with scratch
settings, metadata, object storage and cache. Worker JSON/log/PNG artifacts
live in `renders/e2e`; their harness_sha256 must match the tested source.
Timeouts, native crashes, missing tours/tooltips and unreachable controls are
explicit failures. A failed factory cannot retain an older PNG as evidence.

Native clicks require a visible effective clip and real engine delivery to
the intended context. The recorder maps translated/scaled child painters to
global coordinates, distinguishes independent engines with identical IDs,
opens actual AutoForm folds and scrolls reachable controls. Tour checks walk
introductions and operate the first real awaited target; duplicate labels
resolve through authoritative geometry/context, and ambiguity fails.
Field text retained for interaction is private to the worker, not serialized.
OS dialogs cancel; service/network and external-process actions remain
guarded. Slow local computations must expose a working Cancel/Stop control.

Re-derive the harness regressions with
`pixi run -e test python -m pytest test/e2e/test_click_all_harness.py -q`
(36 passed), and select real plugin cases with `-k <plugin_id>` on the click-all
file. A complete plugin matrix remains a programme gate after the owning
workstreams supply tours, demos, reachable layouts and source prerequisites.
The C27 matrix and intermediate hash runs are diagnostic, not acceptance.


## Reader settings at the existing shell seam

`ReaderSettingsApp` renders a reader's declared native JSON or typed ModelView
through the existing section registry. The actual reader remains its model,
so values and callbacks update the scientific owner. The settings dock uses
ControlHost for a reader without a legacy controller and reuses its live host.
The declaration is validated before installation; unsupported legacy customs,
plots or session curve actions are reported rather than omitted.

Native file/folder and MMFDB data-source inputs retain typed values, Browse,
Database, callbacks, read-only state, cancellation and drops. Session curves
are distinct from database file paths; the old curve_input index/name/action
contract requires its own group-member/API selector integration. Closing a
view prevents delayed database delivery from changing the reader.

Verify the prerequisite with the two targeted reader_settings host test files
(20 passes). The captured CSV supported subset is a host proof, not the complete
CSV migration; its format/error/custom controls remain in the legacy controller
until the full reader declaration is ported.


## Retired unused photon sample widget

The uncalled SpcFileWidget and its dedicated Designer file are removed.
Photon reading, CSV inputs and native reader settings retain their existing
interfaces. A real BH SPC132 baseline and control inventory are retained in
the release-readiness evidence; this approved dead-widget deletion introduces
no replacement window.
