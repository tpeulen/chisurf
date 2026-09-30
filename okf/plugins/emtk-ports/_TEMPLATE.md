# emtk port report — `<plugin id>`

Copy this file to `okf/plugins/emtk-ports/<id>/REPORT.md` and fill **every** section.
"Paste" means the literal output of the command in a code block. An empty section is
not allowed: write `none` and why. Numbers not produced by a command are not accepted.

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | |
| Port type (A adapter / B Qt-only) and why | |
| Agent / date | |
| Effort spent (hours) | |
| Commits (hash + subject, 3 expected) | |
| Agent-board entry | |

## 1. State at start (P1)

Paste `git status --short -- chisurf/plugins/<group>/<id>`:

```
```

Files in the plugin I did **not** write but had to edit: `none` / list + why.

## 2. What the Qt tool offered — control checklist (P0/P1)

One row per control the user sees (labels, buttons, menus, tabs, dialogs, context menus,
shortcuts). Fill "emtk equivalent" after P7.

| # | Qt control (as shown) | Where (tab/menu) | emtk equivalent (spec attr / action / hand-drawn) | Present? |
|---|---|---|---|---|
| 1 | | | | yes/no |

Screenshots taken (file names): `before.png`, …

## 3. Files

| File | New / changed | Purpose |
|---|---|---|
| `gui/model.py` | | |
| `gui/<name>.view.json` | | |
| `gui/app.py` | | |
| `gui/guide.json` | | |
| `gui/help.md` | | |
| `test/test_emtk_<id>.py` | | |
| `manifest.json` | changed | added `entrypoints.emtk` (last change) |

Qt files left untouched (legacy, removed later by the reviewer): list.

## 4. Automated evidence (paste)

`compare` (exit code must be 0):

```
```

`after` summary line:

```
```

`qt_free` result (from `after.json` → `qt_free`):

```
```

Controls without tooltip (`after.json` → `controls_without_tooltip`, must be `[]`):

```
```

## 5. Deliberate differences

Every entry of `compare.json` → `explained` (from `deliberate.json`) and every change of behaviour must appear here. `lost` must be `[]` and `stale_explanations` `[]`.

| Lost/changed item | Why | Where it went / what replaces it |
|---|---|---|
| | | |

If `explained` is empty: write `none — compare.json lost = [] and explained = {}`.

## 6. Tests (paste)

Full plugin test folder:

```
$PY -m pytest chisurf/plugins/<group>/<id> -q -p no:cacheprovider
```

Tool self-test:

```
$PY -m pytest test/gui/test_emtk_port_parity.py -q -p no:cacheprovider
```

| Required test | Test name | What it asserts |
|---|---|---|
| 1 model reference result | | |
| 2 actions and errors | | |
| 3 spec keys exist | | |
| 4 draws empty + populated, both sizes | | |
| 5 main action end to end | | |
| 6 Qt-free | | |
| 7 tooltips | | |
| 8 persistence round trip | | |

Deliberate-breakage check (break behaviour once, see the test fail, restore):

| Test | What I broke | Test result when broken (paste the failing line) |
|---|---|---|
| | | |

Pre-existing failures I did not cause (command + output) or `none`:

## 7. Screenshots I looked at (file → what I saw → what I fixed)

| File | Observation | Fix applied |
|---|---|---|
| `after_1200x800.png` | | |
| `after_800x600.png` | | |
| `after_populated_1200x800.png` | | |

Statement, per screenshot, that none of these is visible: clipped label, text running
past its box, overlapping windows, empty panel, plot without axes, oversized status box.

## 8. Workflow walk-through

The steps a user takes (5–10 lines), and for each the model/app call it maps to and the
result. State the data file used (path under the plugin's test data).

## 9. Persistence, guide, help, docs

* `export_settings()` keys vs the Qt tool's remembered keys:
* Guide steps (count) and which control each targets; each `await` verified by a test or
  by calling `tour.notify_used(<name>)`:
* Help links checked (paste the guardrail test name and result):
* Docs changed (paths) / Docs gaps:

## 10. Blocked / open questions

Anything you stopped on (see the PRD's "When to stop and ask"), with a five-line
reproduction if it is an emtk issue. `none` if nothing.

## 11. Self-check against the Definition of Done

- [ ] D1 `entrypoints.emtk` → Qt-free `make_app()` (section 4 qt_free)
- [ ] D2 every Qt control present or explained (sections 2, 5)
- [ ] D3 no untooltipped control (section 4)
- [ ] D4 four screenshots read, nothing clipped (section 7)
- [ ] D5 workflow tested (sections 6, 8)
- [ ] D6 persistence (section 9)
- [ ] D7 guide + help (section 9)
- [ ] D8 docs (section 9)
- [ ] D9 plugin tests green (section 6)
- [ ] D10 report complete, evidence committed, board updated

## 12. Reviewer quick check (do not edit; copied from the PRD)

```bash
cd ~/dev/chisurf && export QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD:$HOME/dev/emtk"
PY=~/mambaforge/envs/arm64/bin/python
$PY -m test.gui.emtk_port_parity after   <id> --out /tmp/review_<id>
$PY -m test.gui.emtk_port_parity compare <id> --out okf/plugins/emtk-ports/<id>; echo "exit=$?"
$PY -m pytest chisurf/plugins/<group>/<id> -q -p no:cacheprovider
grep -rn "qtpy\|PyQt\|PySide\|chisurf\.gui" chisurf/plugins/<group>/<id>/gui/app.py chisurf/plugins/<group>/<id>/gui/model.py
```
