# alex_suite — emtk port report (accepted 2026-10-03)

Owner rule (AGY_ACCEPTANCE.md): a port is accepted only with (1) screenshots read by the
reviewer, (2) real-click tests on every interactive control, (3) parity evidence, (4) green
suites — then the plugin is swapped off the gate.

## What the app is

`AlexSuiteApp` (gui/app.py): a three-tab linear workflow over the Qt-free view models —
Alternation detection (channel routing, period, folded-phase plot, gates), Titration
(series data_table with typed concentrations, shared-shape Gaussian fit, binding isotherm),
Legacy Export (the five ALEX-Suite CSV files). Entrypoint declared in manifest.json:
`chisurf.plugins.burst.alex_suite.gui.app:make_app`.

## Verification (this acceptance)

- **Screenshots (read):** 15 PNGs in this folder — before.png (Qt tool at 1200x800) and
  after_{alternation,titration,export}_{empty,populated}_{800x600,1200x800}. All three tabs
  render complete control sets: tabs bar, channel fields, phase plot with axes, series table,
  fit headers, checkboxes, Write/Help buttons, live status line. The export tab's lower third
  is empty space (short form, top-aligned) — inspected, not a defect. Captured with the env's
  emtk bumped to main@4315623 (older emtk crashed painting the header: float RGBA through
  QColor).
- **Real-click tests:** tests/test_emtk_clicks.py — 6 tests: tab switching by click,
  Donor/Acceptor channel fields take typing (label-right layout), export checkboxes toggle,
  Write button reaches run_export on a real burst table, Help opens its window, titration
  concentration cell accepts a typed value through the table cell editor.
- **Parity:** compare.json — nothing lost, qt_free OK. `before_controls: 0` is expected: the
  "Qt" baseline is itself emtk-hosted (the Qt tool embeds ControlHost surfaces), so the Qt
  findChildren inventory cannot see its controls; parity rests on the screenshots + the
  38 Qt-free model tests + click tests.
- **Suites:** 64 passed (plugin tests incl. api/alternation/workflow + click tests, gate,
  port parity).

## Fixes made during acceptance

- capture_emtk.py: imported `write_burst_table` (never existed) — writes delimited tables
  inline now; test_api import removed (pytest at module level breaks standalone runs).
- pixi.lock: emtk pinned to main@4315623 (float-colour fix the header paint needs).

## Where to pick it up

- The gate holds only `code_editor` (29 missing Qt controls, emtk im.text_editor gaps).
- Remaining queue: fret_docking, fps_json_editor, burst_analysis, burst_selection, acq,
  mmfdb_admin, quenching_estimator (see roadmap Track B / agent board).
