---
type: Subsystem
title: Help buttons and guided tours
description: The `?` and **Guide** pair every modern plugin carries — one explaining what a control means, the other saying which control to touch first — attached through one shared mixin so any tool can have them, and enforced by a shrinking allow-list.
resource: chisurf/gui/widgets/tools/help_guide.py
tags: [gui, qt, help, documentation, onboarding, plugins, conventions]
timestamp: '2026-08-04T00:00:00Z'
---

# Where to pick this up

**The measurement.** `pytest test/test_plugin_help_guide_seam.py` — the number
that matters is the line count of `test/plugin_help_guide_allowlist.txt`
(`grep -c '^chisurf' test/plugin_help_guide_allowlist.txt`). It went **105 → 96
→ 93 → 92 → 91**; 109 plugins declare a `gui` entrypoint. Regenerate the list from the tree
with the `gui_plugins()` helper in that test file rather than by hand — a plugin
whose `entrypoints.gui` names a *package* rather than a module resolves to that
package's `gui/` subdirectory, not to the folder you would guess, and
hand-editing puts the entry where no lookup will find it.

**Done, with real content:** burst analysis, accurate FRET, burst GS, burst
selection, decay analysis, TTTR Tools, FCS filter calculator, burst background,
burst IRF & background, **2CDE, BVA, H2MM, 2D-FLCS, lifetime-FCS simulator**.

**Prefer a tour that walks on a demo the plugin generates itself.** 2D-FLCS is
the model: its *Simulator* panel makes a two-state exchanging stream whose answer
is arithmetic — τ = 1 and 3 ns with k₁₂ = 30 s⁻¹, k₂₁ = 10 s⁻¹ gives populations
0.25/0.75 and a 25 ms relaxation — so the tour states the answer *before* pressing
Run, and the default 1 ms lag then demonstrates the real lesson (a lag 25× below
the exchange time shows no cross-peaks, and that is not a failure). `fcs_lfcs_sim` now
carries the same shape (τ_D = w₀²/4D puts its two species at 2.8 µs and 45 µs
before anything is pressed), and `synthetic_decay` can too.

**A hand-built panel needs `objectName`s before a tour can point into it.** The
`{"attr"}` / `{"key"}` targets only resolve against an AutoForm view spec, and
most of the burst tools are hand-built Qt. Give the two or three controls the
tour actually names an `objectName` — prefixed, because `{"name": …}` matches by
**suffix**, so a bare `"seed"` also finds the decoder's own seed box. `2cde`
(`twocde_*`) and `h2mm` (`h2mm_*`) are the worked examples.

**A tool with its own `HelpDialog` loses it.** BVA and H2MM each carried their
help as an HTML literal plus the CLI `--help` output inside a `QDialog`. Both are
deleted in favour of `help.md` behind the shared `?`, as burst selection was
before them. When a tool builds its own toolbar and already right-aligns with a
spacer, set `toolbar.setProperty("_chisurf_right_spacer", True)` — two stretches
share the slack rather than adding, and the pair ends up mid-bar.

**Always walk a new tour with the harness**,
`build_tools/dev_utils/check_plugin_guide.py`. It checks three things no unit
test can: both buttons exist, every step's target resolves, and **no step
scrolls** (i.e. nothing is cut off). The truncation check exists because the
bubble silently cut long steps off mid-sentence for as long as the feature had
existed — see the fit-to-content note below.

```bash
QT_QPA_PLATFORM=offscreen CHISURF_SETTINGS_DIR=/tmp/qa-settings \
PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." \
python build_tools/dev_utils/check_plugin_guide.py --all /tmp/guide-shots
```

Current result: **15/16 tours clean**. The one failure is `PSFCalculator`, which
aborts on plain construction under the offscreen platform for OpenGL reasons
that predate this work — see
[known issues](/references/known-issues.md). Its shipped tour is therefore
unverified.

Running the sweep is *not* a substitute for looking at the PNGs it writes. It
proves a step points at *something*; only your eyes prove it points at the right
thing and that the prose belongs where it sits.

**Next, in priority order** (the user's order: most-used analysis tools first):

1. **`fcs_calculator`, `fcs_merger`** — the rest of the FCS group (`flc_2d` and
   `fcs_lfcs_sim` are done). Both are **wizards**: their `entrypoints.gui` names
   `wizard.py` at the *package root*, so their help files go beside that module —
   `chisurf/plugins/fcs/fcs_calculator/`, not `…/gui/` — which is what the
   allow-list entries already say. Neither has a toolbar; give them a hairline
   `QToolBar` and `attach_help_and_guide`, as `fcs_lfcs_sim` now does.
2. **`irf_estimator`, `maxent_decay`, `tr_anisotropy`, `synthetic_decay`** — the
   decay group. `synthetic_decay` simulates, so again a known-answer tour.
3. **`microscopy/img_*`** — six of them already have `help.md` and need only a
   `guide.json`, which is the cheapest remaining work in the list:
   `img_coloc`, `img_drift`, `img_frc`, `img_tracking`, plus `rics_precision`
   and `core/hmm`.

**What a gap blocks.** Nothing blocks the remaining plugins — the seam is
finished and **all three attachment routes are committed and exercised by a
shipped tool**: `NavigationPanelTool` → decay analysis and TTTR Tools,
`ChisurfDockTool` → burst selection and 2CDE, `attach_help_and_guide` → FCS
filter calculator and H2MM. The work left is content.

## A staged blob in `navigation.py` can still revert the shells

The whole seam landed on 2026-08-04, in `903f1e403` (mixin, guard, harness,
twelve tours) and `b2558fd3d` (`NavigationPanelTool`). Both shells — decay
analysis and TTTR Tools — build their `?` and **Guide**, verified headlessly.

`navigation.py` was committed through a **temporary `GIT_INDEX_FILE`** carrying
only these four hunks, because the file was `MM`: another instance has a partial
revert of it *staged*, and `git commit -- <path>` would have committed their
unfinished work with it. Their staged blob is untouched and still staged — and it
now reads as **−41/+3 against HEAD**, so committing it wholesale would take the
mixin wiring with it and the two shells would silently lose their buttons again.

If that happens, the symptom is only visible by construction:

```python
tool = LifetimeAnalysisTool()
tool._help_button is not None and tool._guide_button is not None
```

`okf/log.md` and `okf/references/known-issues.md` carry other instances' entries
too; append to them and stage **the hunk, never the file**. Building the blob on
`HEAD` rather than on the index matters there — the index held a *stale* log.
See [change tracking](/workflows/change-tracking.md).

**Traps, all of them paid for once already.**

* A tour target that does not resolve **does not fail** — the bubble is shown
  centred, so a whole tour can look authored and point at nothing. Walk every new
  tour with the harness.
* **A resolved target is not a visible one, and the harness cannot tell.** A
  `DockArea` tab closed with `close_mode="hide"` stays in the registry, so a
  `{"tab": …}` step still resolves — to a hidden page carrying whatever geometry
  it had when it was closed. `unresolved=[]` and the spotlight lands on a
  rectangle of unrelated panel. Only the PNG showed it. `_resolve_tab` now calls
  `DockArea.showTab` before returning such a page.
* **A folded panel hides the control just as effectively.** An AutoForm `panel`
  is a `CollapsibleBox`, and a form of any size folds most of them; the target
  still resolves, to a widget with a real geometry that is not drawn, so the
  spotlight lands on a header bar elsewhere in the column. `_reveal` now expands
  it — **and suspends `auto_fold`**, because that setting folds a box when the
  pointer *leaves* it and during a tour the pointer is never on it, so a panel
  opened without that would shut again mid-step. Restored in `stop()`.
* **`CHISURF_SETTINGS_DIR` does not cover `QSettings`.** Tools that persist their
  dock layout through `QSettings("chisurf", "<Tool>")` — BVA, H2MM and most
  hand-built tools — read `~/Library/Preferences/com.chisurf.<Tool>.plist`
  regardless, so a headless QA render inherits *your own* closed tabs. Neither
  `HOME=` nor `QSettings.setDefaultFormat(IniFormat)` redirects it on macOS. To
  judge an authored default, apply it explicitly:
  `area.set_layout_state(Tool._default_dock_layout())` and inspect that. This is
  how "the authored layout is broken" was ruled out — it was not.
* Restoring a hidden dock used to put it in **whichever stack `findChildren`
  returned first**, including a stack `deleteLater`-ed by a layout rebuild but not
  yet destroyed. A settings page then rendered at its last standalone size *on
  top of* the real docks. `find_main_tab_widget` now skips anything outside the
  layout tree, and `hideTab` records the stack a page came from so `showTab` can
  put it back. Pinned by `test/gui/test_dock_area.py`.
* Do **not** let the harness *press* an awaited control. `toolAction_add` opens a
  modal file dialog and hangs a headless run forever. Mark the step satisfied
  instead — that is what the shipped harness does.
* Do **not** run `--all` in one process. The OpenGL-backed tools abort under the
  offscreen platform and take the sweep down with them; the harness forks per
  tool for exactly this reason.
* Set `CHISURF_SETTINGS_DIR` to a scratch directory when judging a GUI
  headlessly, or a persisted dock layout restores itself over the authored one.
* Check `sysctl vm.swapusage` and `pgrep -f pytest` before starting a suite —
  other agent instances share this machine, and a second concurrent run fills
  swap and produces crashes that look like code defects.
* `{"key": …}` and `{"attr": …}` are different namespaces. A custom section
  declared `{"key": "path_list", "target": "files"}` answers `{"attr": "files"}`,
  **not** `{"key": "files"}`. The guardrail now tells you which spelling to use.

# Why it exists

A scientific tool has to answer two questions, and they are not the same one.

*What does this control mean?* is answered by long-form help behind a small `?`
button — behind it, not inline, because a panel that explains itself in
paragraphs has no room left to be a panel.

*Which control do I touch first?* is not answered by that at all. A dense panel
of correct, well-documented settings is still unusable if nothing says where to
start, and this is where a scientific tool loses people. That is the **guided
tour**: it points at one real widget at a time, says why it is there, and waits
for the user to press it.

Both used to live on `ChisurfDockTool`, which made them a feature of a base
class rather than of ChiSurf: a tool built on a plain `QMainWindow`/`QWidget`, or
on `NavigationPanelTool`, had no seam at all — roughly thirty tools that could
not have the buttons however much they needed them. They now live in
`chisurf/gui/widgets/tools/help_guide.py`, as a mixin plus a free function.

# The three ways in

Ordered by how little code they need.

**Nothing at all.** `HelpGuideMixin` is mixed into `ChisurfDockTool` *and*
`NavigationPanelTool`, both of which call `ensure_help_toolbar()` themselves. A
plugin gets both buttons by shipping `help.md` and `guide.json` beside the module
its `entrypoints.gui` names — no code change anywhere. A tool that ships neither
gets **no toolbar**, rather than an empty strip of chrome.

**One call.** A tool that builds its own toolbar calls `add_toolbar_help(...)`,
which right-aligns the `?` and adds **Guide** beside it when a tour exists.

**A free function.** `attach_help_and_guide(window, toolbar_or_layout, …)` does
the same for a window that cannot take the mixin — an already-built `QDialog`, a
`.ui`-loaded tree, a plain `QWidget` tool such as the FCS Filter Calculator.

Resources resolve relative to (1) the model's view spec, (2) the model's module
directory, (3) **the tool class's own MRO module directories**. That third anchor
is what makes the zero-code path work for a tool with no model at all, since
`gui/tool.py` sits beside `gui/help.md`.

# What a tour can point at

`guided_tour.py` resolves a step's `target` by any of:

| key | points at |
|---|---|
| `attr` | the model attribute a view-spec field is bound to |
| `key` | a `custom` section's key |
| `title` | a section's title — **including a `panel`**, which is the natural grouping to name |
| `action` | a toolbar action's text; falls back to a plain button's text *or tooltip*, which is how the icon-only shared action bars are found |
| `name` | a widget's `objectName`, exactly or by suffix, case-insensitively — `{"name": "run"}` finds `toolAction_run` in any tool using the [shared action vocabulary](/subsystems/gui-action-vocabulary.md) |
| `tab` | a dock tab or `QTabWidget` page — ChiSurf tools are built out of these far more often than out of view specs |
| `panel` | a row of a `NavigationPanelTool`'s left navigation list, so a *hub* tool's steps can be its panels |

`await` makes a step wait for the user to use the highlighted control. There is
deliberately no "do it for me": someone who watched a button being pressed has
not learned where it is.

## The failure mode this design is built against

A step whose target does not resolve is **shown centred rather than skipped** —
so a wrong target never crashes and never disappears. It silently degrades the
tour into the slideshow the format exists not to be, and no construction test can
see the difference. That is why the resolver grew `panel`, `tab`, `name` and the
button-tooltip fallback rather than tours being written around what happened to
work, and why `test_plugin_help_guide_seam.py` checks targets statically against
the view spec.

Two traps found by rendering it rather than by reasoning about it:

* A **waiting panel step whose row is already current** strands the user — a list
  emits nothing when you select the row you are on, and the first panel of a
  workflow shell is always current. Such a step is now satisfied on entry.
* `HelpButton(align="right")` adds a stretch **inside itself**, which competes
  with the toolbar's right-aligning spacer; the two share the slack and strand
  **Guide** mid-toolbar. Inside a toolbar the button is added with no alignment
  of its own.
* The bubble **cut long steps off mid-sentence**, with the buttons drawn neatly
  underneath — indistinguishable from a step written that way.
  `adjustSize()` cannot size word-wrapped rich text, because the label's
  `sizeHint` does not know the width it will wrap to. `_Bubble.fit_to_content`
  fixes the width first, measures with `heightForWidth` at the width the body
  *actually* gets (minus the scroll bar, which otherwise costs a line), then
  **corrects from the measured scroll-bar range** — `heightForWidth` is itself
  only an estimate for rich text and under-reports by a line or two. A step that
  genuinely cannot fit scrolls rather than pushing *Next* off-screen.

The `key` / `attr` namespaces are also kept apart in the guardrail. A custom
section is declared `{"type": "custom", "key": "path_list", "target": "files"}`:
`files` answers `{"attr": …}` and `path_list` answers `{"key": …}`. Pooling them
let `{"key": "files"}` pass the static check and resolve to nothing at run time.

# The rule, and how it is enforced

`test/test_plugin_help_guide_seam.py` enumerates every plugin whose manifest
declares a `gui` entrypoint and requires both files.
`test/plugin_help_guide_allowlist.txt` is a **shrinking** record of the
not-yet-modernised, in the same spirit as the
[chiplot](/subsystems/chiplot.md) migration list: a modernised plugin that stays
listed fails as a stale entry, and an unlisted plugin without the files fails as
a regression. Adding a line is never the fix. The end state is an empty list.

Shipped files are checked for substance, not just presence: a guide must have at
least three steps, every step a title and text, at least one step an `await`, and
its `attr`/`key` targets must exist in the view spec. A help page must clear a
minimum length and every relative Markdown link must resolve — help links are
live, routed to the documentation browser, so a dead one is only discovered by
clicking it.

# See also

* [GUI & AutoForm](/subsystems/gui-autoform.md) — the `help` section this reuses.
* [Toolbar action vocabulary](/subsystems/gui-action-vocabulary.md) — the
  `toolAction_*` object names `{"name": …}` targets.
* [Testing workflow](/workflows/testing.md) — why a GUI change is unfinished
  until the PNG has been looked at.
