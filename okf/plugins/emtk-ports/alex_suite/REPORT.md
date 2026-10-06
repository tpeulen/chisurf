# emtk port report — `alex_suite` hub (DONE 2026-10-06, T-20261006-ALEXHUB)

(Written by the coordinator from the porting agent's hand-back; subagents may not write
report files. The 2026-10-03 report of the earlier, partial port follows below as history.)

The ALEX Suite opens as a native emtk hub: `chisurf/plugins/burst/alex_suite/gui/native.py`
(`AlexHubApp`, built on Burst Analysis's `BurstAnalysisHubApp` and `ToolHubApp`), manifest
`entrypoints.emtk`. The owner asked for "a simple workflow": seven numbered steps walked with
Next, plus four side tools. On the demo measurement, getting from files to an E–S histogram
needs only Next presses.

## The workflow

Rail, under "Pipeline steps":

1. **Setup** — PIE users pick their setup; µs-ALEX users leave it as it is.
2. **Files** — drop files, or press Load demo data.
3. **Alternation (optional)** — µs-ALEX data is detected and converted on arrival. The
   converted container and the setup "ALEX Suite (auto)" go to every later step. PIE data is
   left alone, and the step says so.
4. **Burst search** — Next runs it and waits.
5. **Background** — estimated on arrival.
6. **Accurate FRET** — the run loads on arrival; Next calibrates.
7. **E–S histogram** — ndX opens with E against S on [-0.1, 1.1].

Under "Side tools": Burst properties, Titration (seeded with the bursts and γ/β), BVA, and
Export (ALEX-Suite CSV). `>>` walks all remaining steps. The status line says what the
current step needs. `gui/guide.json` has 13 steps; 9 of them wait for the user to press the
real Load demo data or Next button.

## Commits

5fb106e49 (Qt baseline) · a577affef (AS1, alternation model + demo) · 4f6add194 (AS3, export
model; `.pto` export fixed) · 5d54f60de (AS2, step apps, titration) · 5912033fa (AS4 hub;
Accurate FRET and browser accept a run inside a `.pto`) · 4e51d24fe (status line, evidence,
guides) · 7eddfcb21 (OKF) · 0e3c808b6 (tour targets).

## Walk-through (asserted by `tests/test_emtk_native_hub.py`)

On the demo data:

- Alternation: period 8000, gates 235–3685 / 4235–7685, donor 0 / acceptor 1.
- Burst search: 462 bursts.
- Accurate FRET: α 0.009, δ 0.067 (planted 0.06), γ 0.94, β 1.10.
- E–S histogram: two FRET populations at S ≈ 0.5.
- The export writes 4 CSVs next to the container.

On the PIE fixture, the alternation step leaves the data alone and the search finds 198 bursts.

## Parity

Before: 402 controls (the Qt shell at every step). After: 1880 controls, none without a
tooltip, Qt-free. `compare`: lost 0. 94 differences are explained in `deliberate.json`:

- The legacy Burst Selection is mapped onto the native app.
- Renames:
  - "3. Alternation (µs-ALEX)" → "(optional)"
  - "Next ▶" → "Next"; "⏩ Run" → ">>"
  - "? Help" → "Help" + "Tool help"
  - "Proceed to Burst Selection" → "Proceed to 3. Alternation"
  - the Qt hint "pick them in step 1" now correctly says "2. Files"
- The "Static FRET line" overlay is in ndX's Overlays tab.
- ndX's Gaussian Fit tab opens from View › Fit Gaussians.
- On PIE data the step does not run a detection on arrival; Detect only is still there.
- Data of the before-image and re-wrapped text.

## Screenshots read

`after_steps/*` (every step empty and populated, 1200x800 and 800x600), `before_steps/*`, the
guide card, the help window, `docs/guides/figures/alex_suite_hub.png`. The coordinator re-read
the last one. Fixes they led to:

- a literal `&gt;` on the tour card;
- export field widths;
- the alternation dock split at 800 px;
- the rail badge;
- ndX axes and range (Duration on Y, x-range -134);
- the status text width, which had disabled Back and Next.

## Tests

| Suite | Passed |
|---|---|
| alex_suite | 72 |
| hub_membership | 7 |
| ribbon_layout | 12 |
| plugin_menu_tabs | 4 |
| plugin_registry | 23 |
| ribbon_layout_build | 1 |
| burst_analysis | 49 |
| accurate_fret | 58 |
| burst_browser | 17 |
| help_guide_seam | 293 |
| emtk_port_parity | 13 |

The committed tree, run in a worktree: 79 passed. Failing before this work (other lanes):
test_prd_mentions (stale allowlist line), test_guided_tour (cookiecutter link),
test_ui_schemas (ndX / ptu_alex_creator).

## Docs

`gui/help.md` ("The simple workflow"), `gui/guide.json`, `docs/guides/66_alex_suite.md`
(figure `figures/alex_suite_hub.png`), `docs/guides/27_alex_smfret_workflow.md` (GUI tip).

## Where to pick this up

1. Retire the Qt shells: `alex_suite/gui/tool.py` and its panels,
   `tests/test_workflow_shape.py`, `tests/test_ndx_step.py`, the three-tab `AlexSuiteApp` in
   `gui/app.py`, and Burst Analysis's Qt shell. Coordinate with the typed-field lane, which
   has uncommitted edits in `app.py` and an untracked test that drives `AlexSuiteApp`.
2. `ToolHubApp`: a status text wider than its room covers Back / >> / Next, which then stop
   taking clicks. It is worked around in `AlexHubApp._fit` only; the fix belongs in
   `tool_hub.py` (emtk-port session). In `known-issues.md`.
3. The help window renders markdown emphasis raw (affects every help page). In `known-issues.md`.
4. The shared setup step's button reads "Proceed to Data Selection" in the ALEX rail.

---

## History: the 2026-10-03 report

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
