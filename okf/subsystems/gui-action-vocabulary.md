---
type: Subsystem
title: The shared toolbar action vocabulary
description: One canonical icon, colour, tooltip and toolbar position per semantic action, so the same function is the same button in every plugin — including the transport controls (run, restart, pause, stop) that drive a long computation.
resource: chisurf/gui/widgets/tool_buttons.py
tags: [gui, qt, toolbar, icons, glyphs, conventions]
timestamp: '2026-07-28T00:00:00Z'
---

# Why it exists

Every plugin grew its own toolbar, so the same function looked different in each
one: Run was a rocket here and a green "▶ Run" caption there, Clear was a
dustbin in one tool and the word *Reset* in another, and a user who had learnt
one panel had learnt only that panel. The vocabulary makes the mapping from
*action* to *button* a single decision made once: an action has one icon, one
accent colour, one canonical tooltip and one left-to-right position, and a
plugin asks for it by name.

```python
from chisurf.gui.widgets.tool_buttons import TOOLBAR_STYLE, action_button

toolbar.setStyleSheet(TOOLBAR_STYLE)
toolbar.addWidget(action_button("run", tooltip="Fit H2MM on all loaded bursts"))
```

Buttons are **icon-only**: the detail belongs in the tooltip, which is composed
as `"<canonical label> — <tool-specific detail>"`, so the shared meaning is
always stated first and the panel-specific meaning second. Each button carries a
stable `objectName` (`toolAction_<key>`), which is how tests and stylesheets
address it.

# The transport controls

Four actions drive a long computation, and they read as the media controls
everyone already knows rather than as invented iconography:

| Key | Glyph | Accent | Hue | Means |
|---|---|---|---|---|
| `run` | ▶ | green `#2a6a3a` | 135° | start the computation |
| `restart` | 🔁 | teal `#1a6a6a` | 180° | run it again from scratch, even if nothing changed |
| `pause` | ⏸ | amber `#9a6a10` | 39° | suspend a running job |
| `stop` | ⏹ | red `#9a2f2f` | 0° | end a running job; its partial result is discarded |

**The background carries the meaning, not the glyph.** A glyph is small and read
second; the accent is what the eye lands on. `▶`, `⏸` and `⏹` have no colour
presentation in the shipped emoji font — they take the button's text colour, so
they also grey out correctly when the button is disabled — which means the
colour language *has* to live in the background. Each control therefore owns its
own hue, at least 30° from its neighbours.

Two collisions this replaced, both of which put identical buttons side by side:

* `restart` reused `run`'s green, so the two "go" buttons differed only by a
  small monochrome glyph.
* `stop` reused `clear`'s red — and they are adjacent in the BVA toolbar. They
  still share the red *family*, which is right (both end or discard something),
  but are now separated by weight: stop is the bright, saturated red
  (`val 0.60 / sat 0.69`), clear the dark one (`0.42 / 0.60`).

The same weight trick separates `pause` (bright gold) from `save` (dull olive),
which are close in hue. `test/gui/test_tool_buttons.py` pins the hue spacing and
the stop-outweighs-clear relation, so a future accent cannot quietly collide.

**`restart` is not `refresh`.** `refresh` (`🔄`) redraws a view from a result
that already exists; `restart` recomputes the result. They are adjacent in some
toolbars (the burst search has both), their glyphs are both blue circular
arrows, and what tells them apart is the accent: restart is teal, refresh sits
on the muted `settings` blue-grey. Do not use one for the other.

`pause` is in the vocabulary but wired to nothing: the task layer
(`chisurf/gui/task.py`) offers `cancel()` and `is_running()`, with no suspend or
resume. It is defined so that the first tool with a genuinely pausable job does
not invent its own, not because anything pauses today.

# Drawing attention to one button

`flag_attention(button, on)` outlines a button in amber to mean *this is the one
you want now*. Its only user is `restart`, which is worth noticing in exactly one
situation — straight after a run was skipped because nothing changed — and is
invisible clutter the rest of the time. What does the skipping is the burst
steps' reuse gate (`chisurf/core/analysis_cache.py`), described in
[/plugins/burst.md](../plugins/burst.md).

The accent is applied by **rewriting the button's own stylesheet**, not by
toggling a `[attention="true"]` property selector. A widget that carries its own
stylesheet does not reliably re-evaluate an attribute selector when the property
changes; the first implementation set the property, repolished, and drew no
outline at all — a failure a test asserting on the property would have passed.
`test/gui/test_tool_buttons.py` therefore asserts on the resulting rule.

# Adding an action

Add a `ToolAction` to `TOOL_ACTIONS` with a key, a glyph from
[`chisurf/gui/glyphs.py`](../../chisurf/gui/glyphs.py), a label, a canonical
tooltip, an accent `kind` from `BTN_STYLES`, and an `order` that places it
sensibly relative to its neighbours. A control that drives work needs its **own**
`kind`, not a borrowed one — sharing an accent is what made restart look like
run.

Then **render it and look at it**: glyph size, colour presentation and
confusability with the buttons beside it are not visible in any assertion. A
plain text glyph (`⟳`, `↺`) obeys `font-size` and comes out visibly smaller than
the emoji next to it; prefer an emoji, or accept that the glyph will need its own
size. When judging contrast, check whether the button is *disabled* first —
`:disabled { color: #666 }` greys the glyph, which reads as a contrast bug in a
screenshot and is not one.

# Related

* [/subsystems/gui-autoform.md](gui-autoform.md) — the data-driven form framework
  these toolbars sit above.
* [/workflows/testing.md](../workflows/testing.md) — why a GUI change is not done
  until the rendered image has been looked at.
