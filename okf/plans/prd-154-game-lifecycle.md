---
type: Plan
title: Shared native game lifecycle extraction
description: Behavior-preserving extraction of duplicated lifecycle and frame scheduling from five native game apps.
tags: [games, refactor, testing]
---

# Shared native game lifecycle extraction

## Scope and acceptance

Owner: /root integrates one required `GameApp` base under
`chisurf/plugins/misc/games/_base.py` and adopts it in the five committed game apps.
The approved design is [P-F step9](../prds/prd-154.md#p-f--w6-plugin-uniformity-mechanics).
Exact HEAD candidates preserve foreign source edits. No render/chrome change,
algorithm changes, generic blind saved-field assignment, Number Quest relocation,
new dependency or audio-device activation in this slice.

## Cleanup plan before code

1. Lock the existing behavior first: real modifier/Qt-host input tests, game
   window/state tests, and narrow lifecycle regressions for shutdown, focus loss,
   frame demand and supplied audio resources. Derive per-app predicates from
   committed source; do not guess that every model uses the same input structure.
2. Remove duplication only: share the common lifecycle/frame/audio boundary in
   the required base. Keep explicit leaf hooks for input/repeat/frame clearing and
   running predicates; retain each numerical stepping, renderer and atomic state
   validator. Reuse `gui/keys.py` unchanged for application shortcut protection.
3. Compare old/new rendered command/control inventory and exported state at a
   fixed clock. No recapture for unchanged rendering under A0; a discovered
   layout change instead requires an actual before/default/narrow capture pair.
4. Verify exact candidates, existing regressions and applicable guards. Publish
   one source/evidence archive with the owning concept/log/resume and focused
   plain local commit; no foreign hunks or separate receipt commit.

## Invariants

- Shift/keypad input accepted; Ctrl/Alt/Meta remain application shortcuts.
- Per-game press/release/repeat/second-player rules stay intact.
- Focus loss clears relevant held queues, repeat timers and frame timestamps.
- Closed apps stop animating; pending requested frames remain serviceable while
  idle without running physics or changing pause state.
- Supplied audio is disabled/released at the existing boundary, without rewriting
  the persisted sound preference. Callback-only effects are not a music backend.
- Defaults, window metadata, exported state shape and complete atomic restoration
  remain unchanged. Pong/Breakout numerical step caps remain1/120s.

## Explicit remaining work

Shared binding/state declaration, prescribed chrome/help/restart behavior and
Number Quest consolidation remain open if not closed by this bounded slice.
Default playback/audible sound is also separate from optional-backend cleanup.
Core/acquisition/setup/wizard and family tooltip/literal obligations remain W6f.

## Separate required boundary fixes

Baseline tests must distinguish these from unchanged gameplay: pending requested
frames omitted by Pong/NumberQuest; closed lifecycle/key rejection absent from
Minesweeper; repeated object-audio close; and uncleared Pong second-player pressed
queue. Post-close pointer mutation in Pong must also be blocked before claiming
all input stops. Callback-only Minesweeper audio stays a separate capability; do
not manufacture an object backend or start playback. No focus-regain policy.
Preserve constructor ordering for model callbacks; do not move audio/clock/default
initialization across model construction merely to maximize line deletion.

Actual input baseline nodes live under `chisurf/plugins/misc/games/test/`, including
`test_modifier_keys.py` and `test_game_keys_through_qt_host.py`.

## Verified outcome

Separate review accepted the bounded plan. The committed-subtree baseline20cases
and14required-red boundary cases lead to41independent candidate cases passing.
All five full state/window/render-command snapshots are exactly equal. Existing
input/Qt-host/window/native cases69pass against the same exact candidate overlay.
One minimal GameApp shares lifecycle and optional object-audio methods, with leaf
running/input-clear hooks; constructor ordering and protected algorithms/render/
state validators remain intact.
