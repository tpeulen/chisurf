---
type: Subsystem
title: emtk UI action vocabulary
description: One icon, English source label, tooltip and widget kind for every action the emtk apps share (Help, Guide, Sound, Restart, Run, Save, Open, Browse, Export, Copy, Reset, Cancel, Close, Load example), drawn through one helper and guarded against hand-drawn variants.
resource: chisurf/plugins/emtk_layout.py
tags: [gui, emtk, autoform, conventions, icons, i18n]
timestamp: '2026-10-10T00:00:00Z'
---

# Where to pick this up

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

Item-rect keys, `remember()` names, awaited tour steps and keyboard shortcuts
are not part of the vocabulary and did not change when the apps were ported.

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
