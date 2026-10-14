---
type: Subsystem
title: emtk UI action vocabulary
description: One icon, English source label, tooltip and widget kind for every action the emtk apps share (Help, Guide, Sound, Restart, Run, Save, Open, Browse, Export, Copy, Reset, Cancel, Close, Load example), drawn through one helper and guarded against hand-drawn variants; and the button roles (primary / danger) that colour a panel's main and destructive actions.
resource: chisurf/plugins/emtk_layout.py
tags: [gui, emtk, autoform, conventions, icons, i18n, colour]
timestamp: '2026-10-14T00:00:00Z'
---

# Where to pick this up

Button roles (2026-10-14, emtk 0.1.16):

1. Closed 2026-10-14: LLTF has `▶  Fit` `role="primary"`, `⏹  Stop` and
   `Clear output` `role="danger"`, and Load example drawn by
   `action_button("example")`; `test/test_ui_vocabulary.py` passes (23).
2. Measure hand-drawn emtk buttons without a role: run the AST scan used when
   roles landed. It covers every `im.button` whose `_literal` caption has a
   `verb_role`; 44 sites had none, 28 were given a role. The guard only checks
   declared `button_row` entries, so this scan is the worklist for Python.
   Left neutral on purpose:
   - per-row `Remove##path` buttons in file lists (burst_background, burst_gs,
     burst_irf_bg, clsm), because a column of red buttons is noise;
   - the model section's `compute κ²` button, because it only opens the κ²
     dialog. The dialog's own **Compute** is primary.

   The `self.button(...)` wrappers of bid_to_analysis, microtime_histogram,
   tttr_microtime_shifter and fcs_channel_preset now take a `role`:
   - primary: Process, Apply;
   - danger: Stop, Clear, Remove, Delete preset, Remove this pair.
   - pto_inspector `Fit graph`, which frames the view.
3. Open: the shell has no real light theme. `im.style_colors_light` inverts the
   palette, and the docks keep their own dark fills. The light role variants
   were judged on that inverted style. Re-judge them once a designed light
   palette exists.
4. Trap: `Fit` is not always the main action. It can mean "frame the view"
   (lightpath, globalview `Fit view`) or "take values from a fit" (synthetic
   decay `📥 Fit…`, `🔗 Fit group`, maxent `Fit`). Such entries declare
   `"role": "default"`, or are listed in `NEUTRAL_CAPTIONS`.

Shared actions:

1. Measure: `python -c "import sys; sys.path.insert(0,'test'); import
   test_ui_vocabulary as t; print(t.all_findings())"` lists every remaining
   hand-drawn shared action. Trap: a button row that leads with a key
   (`("Export", tip, lambda: …)`) is not recognised, because its key is often a
   tour target; such rows were ported by hand (spot_finder, channel_definition,
   fcs_correlator, synthetic_decay).
2. Blocked: the emtk pin. `im.toggle_button` and the button-row `icon` live in
   emtk `ed2f6f9`, `cda4a92`, `7f341f9`, `icon_caption` and later (local, unpushed; local HEAD ea91cb3). `pixi.lock` still
   names `3416806a`; the test/docs envs were reinstalled from the local commit.
   An env re-solved from the old pin raises `AttributeError: toggle_button` in
   all five games.
3. Open: ndxplorer (`modules/ndxplorer`, its own repo) draws its own chrome and
   is not scanned; port its Help/Guide/Export to the same table there.
4. Open: the Qt legacy toolbar ([Toolbar action vocabulary](gui-action-vocabulary.md))
   uses `ℹ️` for Help where emtk uses `❓`; align it when that toolbar is next
   touched. Compound captions (`Save JSON`, `Export CSV`, `Process`, `Start`)
   are distinct actions and stay free.
5. Measure: the literal and tooltip allow-lists key findings by line; ported
   files shifted lines, so `test/test_i18n_literals.py` and
   `test/test_tooltips.py` report relocated/stale keys until the root
   regenerates them (they only shrink: ported controls left the measurement).

# Why it exists

The user's report: *"in the game where you guess numbers the sound control
looks different — the apps must have a uniform look across all emtk:
consistent icons, labels, etc."* Measured before the change (AST scan of
every `im.button` / `small_button` / `checkbox` and every declared
`button_row` entry under `chisurf/`):

| Action | Variants that shipped (caption, widget, count) |
|---|---|
| Help | `Help` button ×42, `Help` spec ×15, `❓ Help` ×12, `❓  Help` ×4, `? Help`, `Tool help`, `Open Help`, `❓ Open Help` |
| Guide | `Guide` button ×44, `Guide` spec ×16, `📖 Guide` ×8, `📖  Guide` ×4, `🧭 Guide` |
| Sound | button ×2 (Pong dark, Breakout dark), checkbox ×2 (Tetris, Minesweeper), a hand-painted **light-theme** strip with a light box (Number Quest) |
| Restart | `Restart` ×2, `↻ Restart`, `🔄 Restart` |
| Run | `Run` ×10, `▶ Run` ×3, `🚀 Run`, `⏩ Run` |
| Save | `Save` ×10, `💾 Save` ×7, `💾  Save`, `Save…`, one `small_button` |
| Open / Browse | `Open` ×4, `📂 Open` ×2, `Open…`; `Browse` ×11, `Browse...` ×2, `Browse…` ×2, `📁  Browse…` |
| Export | `Export` ×4, `💾 Export` ×2, `Export…` |
| Copy | `Copy` ×3, `📋 Copy`, one `small_button` |
| Reset | `Reset` ×5, `↺ Reset` ×2 |
| Cancel / Close | `Cancel` ×38; `Close` ×7, `✖ Close`, `✕ Close` |
| Load example | `Example` ×3, `Demo` ×4, `Load demo` ×3, `🧪 Load demo`, `Load example` ×3 |

Tooltips for the same action differed in every window. Each window looked
fine on its own; side by side they read as different products.

# The vocabulary

`chisurf/plugins/emtk_layout.py::ACTIONS` — icons are the canonical glyphs of
`chisurf.gui.glyphs.Glyphs` (spelled out there because importing `chisurf.gui`
loads Qt; a test pins them equal). Labels and tooltips are English source text
translated through `tr()`; their six-locale rows live in
`chisurf/emtk/shared_i18n.py`, which the helper installs on first use.

| Key | Icon | Label | Kind | Tooltip | Tooltip replaceable |
|---|---|---|---|---|---|
| `help` | ❓ | Help | button | Open the help for this window. | no |
| `guide` | 📖 | Guide | button | Start a step-by-step tour that points at the real controls. | no |
| `sound` | 🔊 / 🔇 | Sound | toggle | Music and sound effects (off by default). | no |
| `restart` | 🔁 | Restart | button | Start over from the beginning. | yes |
| `run` | ▶️ | Run | button | Run with the current settings. | yes |
| `save` | 💾 | Save | button | Save the result to a file. | yes |
| `open` | 📂 | Open… | button | Open a file. | yes |
| `browse` | 📂 | Browse… | button | Choose a file or folder. | yes |
| `export` | 📤 | Export… | button | Export the result to a file. | yes |
| `copy` | 📋 | Copy | button | Copy to the clipboard. | yes |
| `reset` | ♻️ | Reset | button | Restore the default settings. | yes |
| `cancel` | ✕ | Cancel | button | Stop or dismiss without applying the change. | yes |
| `close` | ✕ | Close | button | Close this window. | yes |
| `example` | 🧪 | Load example | button | Load a built-in example to try this tool. | yes |

**Why some tooltips are fixed and others are not.** Help, Guide and Sound mean
the same thing in every window, so their tooltip is the same everywhere and the
helper refuses a replacement. *What* a Run runs, a Save writes or a Cancel
discards is the useful part of those tooltips, so a tool passes its own
(`tooltip=tr("Fit every detected region…")`); the label, icon and widget stay
canonical. Sound's unavailable state has one fixed text too: *No sound here:
this window has no audio output.* A shortcut is appended as *Shortcut: M*.

**Ellipsis** marks a label that always opens a chooser (Open…, Browse…,
Export…). **Widget kind**: every action is a full `im.button`; `small_button`
and checkbox variants are gone. Sound is `im.toggle_button` (emtk): a button
that stays in the active colour while on, so it sits in a row of buttons
without reading as a form field and still shows its state.

# How to draw one

```python
from chisurf.plugins.emtk_layout import action_button, sound_toggle

if action_button("help"):                 # canonical icon, label, tooltip
    self.help_window.show()
self.item_rects["help"] = im.get_item_rect()   # tour targets unchanged

if action_button("save", tooltip=tr("Write the merged curve.")):
    self.save()

if sound_toggle(self.sound_enabled, available=self.audio is not None, shortcut="M"):
    self.set_sound()                       # the caller owns the state flip
```

Declared rows carry the same entry (`action_item("help", "open_help")` builds
it): `{"label": "Help", "icon": "❓", "action": …, "description": …}`. The emtk
form renderer and the Qt `ButtonRowWidget` both draw `icon` in front of the
translated label (`emtk.view_form.icon_caption`, which also drops the U+FE0F
presentation selector the atlas cannot draw).

Caption icons are drawn in colour (emtk `605e7d4`). The real painters (GPU
`QuadPainter`, `PilPainter`, `PixelPainter`) split a caption with
`emtk.icons.pictogram_runs`: each colour emoji cluster -- including a leading
pictograph whose U+FE0F `icon_caption` dropped (`⚙ Settings`) -- is drawn by
`icons.draw_icon` in one small `icon_box` (a line high), the rest as text.
`text_width` measures the same runs (`icons.caption_width`), so buttons are
sized to what is drawn. Recording painters still record the whole caption, so
`action_caption(...)` clicks are unchanged; the icon also appears in
`painter.icons`. Glyphs with no colour form (◐ ✕ › ▶) stay text-colour masks;
the icon takes the text colour's alpha, so a disabled button fades it. Known
limit: the monospace text editor positions by cell, so an emoji typed into it
is drawn wider than its cell. Wider captions pushed the image browser toolbar
1 px out of an 800 px window; emtk `e7ba04d` caps a control alone on its line
at the line and wraps a button row evenly.

Item-rect keys, `remember()` names, awaited tour steps and keyboard shortcuts
are not part of the vocabulary and did not change when the apps were ported.

# Button roles: colour says what kind of action it is

The owner's report: *"the fit btn lacks color, some colors improve the ux"*.
Every emtk button was drawn in the same slate. Seven plugins painted their
headline action green by hand (`push_style_color(Col.BUTTON, ACCENT_GREEN)`,
or a `"colours"` tuple in `button_row`). The shell's Fit had no colour at all.

**emtk (0.1.16).** `im.button(label, size, role=...)` and a declared
`button_row` entry's `"role"` colour a button from the theme:

| Role | Meaning | Dark fill / hover / held | Light fill / hover / held |
|---|---|---|---|
| `primary` | the one main action of a panel (Fit, Run, Compute, Start) | 38,104,196 / 44,112,206 / 28,88,170 | 25,103,210 / 21,90,190 / 13,71,161 |
| `success` | a confirming action (`action_button(accent=True)`) | 28,120,56 / 34,134,64 / 24,104,48 | 30,126,58 / 26,112,52 / 20,96,44 |
| `danger` | a destructive action (Delete, Remove, Clear, Stop) | 156,52,52 / 172,60,60 / 136,44,44 | 176,48,48 / 158,40,40 / 136,32,32 |
| `default` / none | everything else | the theme's button colours | |

- **Theme.** `emtk.style.BUTTON_ROLES` holds a `ThemedButtonRole` per role. The
  variant is picked from the window background's lightness, like
  `ThemedAccent`.
- **Contrast.** White text keeps WCAG AA (≥ 4.5:1) in every state.
- **Disabled.** A disabled role button is drawn with 30 % of its fill mixed
  into the neutral button colour, dimmed, with the theme's dimmed text. It
  reads as unavailable, not as a faint live button.
- **Focus.** The focus ring takes the text colour, because the theme's blue
  ring vanishes on a primary fill.
- **Restyling.** An application can give a role its own colours with
  `set_button_role`.
- **Rejected colours.** The first danger red, 186,48,48, read as an alarm on
  the full-width *Remove dataset* bar, so it was deepened.

**The vocabulary decides.** These live in `chisurf/plugins/emtk_layout.py`:

- `PRIMARY_VERBS`: run, fit, compute, calculate, simulate, start, search,
  analyse, process, optimise.
- `DANGER_VERBS`: delete, remove, clear, stop, abort, discard, purge, erase,
  wipe. `unlink` is not in the list: unlinking can be undone.
- `NEUTRAL_CAPTIONS`: `Fit view` and `Clear selection`.
- `verb_role(caption)`: the role these give a caption.

How the role reaches each kind of button:

- `ACTIONS["run"]` carries `role="primary"`, so every `action_button("run")` is
  primary, and `action_item("run", …)` writes the `role` into a declared row.
- The hand-drawn `button_row` helper takes an entry's `role`. Without one it
  uses `row_roles`: the vocabulary's role, with only the first primary
  candidate of the row made primary. Its old `colours` key is gone.
- Declared specs spell it out, as `"role": "primary"` / `"danger"`, or
  `"default"` for an exception. 104 entries in 59 `*.view.json` files were
  set from the vocabulary. Among them, the Analysis dock's **Fit** is primary
  and **Remove fit** and **Remove dataset** are danger.

**Guard.** `test/test_ui_vocabulary.py` checks every declared container:

- every role is a known one;
- there is at most one primary;
- a destructive caption declares `danger`;
- a panel whose buttons include a main-action verb declares a primary.

It also pins Fit/Remove fit in `emtk/views/analysis.view.json` and checks
that no shipped file pushes its own button colours.

Screenshots judged (headless, arm64):

- the shell with a TCSPC Lifetime fit, dark and inverted-light: Fit blue,
  Remove fit and Remove dataset muted red;
- tttr_splitter: Convert / Split and Start batch blue, Clear red;
- burst_2cde: Run blue, Stop red;
- pch: Compute PCH disabled, which reads disabled;
- hmm: Fit disabled before data.

# The games

All five games draw Sound through `sound_toggle` at the same spot (x+4, y+2) in
the dark theme; Number Quest's hand-painted light strip is gone. Breakout has
no audio backend but has always let its Sound preference be switched, so it
passes `available=True` and keeps that behaviour. The shared Help / Restart /
Guide header (`chisurf/plugins/misc/games/game_header.view.json`) carries the
canonical icons; Restart keeps its game-specific tooltip; the header fit
measures captions with their icons.

# The guard

`test/test_ui_vocabulary.py` scans `chisurf/**/*.py` (outside tests and the
helper) for widget calls and `button_row` dicts whose caption — through `tr()`,
concatenation, f-strings or `icon_label` — normalises to a shared action, and
every `*.json` `buttons` entry for a non-canonical label, a missing/wrong
`icon` or (fixed actions) a non-canonical description. It also pins the icons
to `Glyphs`, checks every label and tooltip has a shared-catalogue row, and
that the helper module stays Qt-free. Held files are named with a reason and
the list can only shrink.

See also: [Toolbar action vocabulary](gui-action-vocabulary.md) (the Qt
counterpart), [Help buttons and guided tours](gui-help-and-guides.md),
[Games](chigame.md), [i18n](i18n.md).
