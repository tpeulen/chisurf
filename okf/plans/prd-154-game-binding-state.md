---
type: Plan
title: Shared game binding and scalar state contracts
description: Remove repeated binding resolution and scalar export while retaining exact per-game precedence and atomic nested state validation.
tags: [games, refactor, testing]
---

# Shared game binding and scalar state contracts

## Cleanup plan before code

This is one duplication-focused P-F9 slice under the existing direct execution
lane and ai-slop-cleaner. Owner six files: GameApp base and five canonical apps.
Separate test writer first captures exhaustive committed binding behavior and
state exports/round-trip/late-failure immutability; no implementation before lock.

1. Declare ordered plain BINDINGS entries; one GameApp resolver matches physical
   integer keys or normalized text in the declared order. Preserve each unbound
   shape, second-player tuple and direction tuples. No injected shortcuts.
2. Promote existing Breakout/Pong/Tetris scalar tuples to classFIELDS; share only
   their scalar comprehension and reuse it in current validation. NumberQuest
   andMinesweeper spans/derived representations retain explicit codecs.
3. Expose each existing atomic validator as prepare-candidate then explicit
   commit, without changing validation/coercion expressions or post-restore
   input/frame/audio policy. No genericblind setattr or thin restore wrapper.
4. Exact committed before/owned after binding matrices, complete numeric/export/
   render/control snapshots and late failure identity/state/input/audio checks
   prove parity. Freeze guards/static checks and one source/docs/evidence commit.

## Corrections to the older recipe

Pong precedence is physicalUp/Down, thentext, thenEnter fallback; other apps may
giveEnter priority. Preserve conflicting inputs such as binding(KEY_RETURN,'p').
Application shortcuts remain guarded outside resolution. Input storage, repeat,
zero-time actions and all numerical stepping/render code remain local.

FIELDS is a scalar declaration where meaningful, not permission to flatten nested
rounds. Brick/particle, board/rotation/collision, winner/score/spectrum, history
replay and adjacency/cursor validators are stronger than a generic field copier.
Their existing strictness and permissive coercions both remain unchanged.

## Remaining obligations

This closes only meaningful shared binding/scalar and atomic-prepare contracts.
Common chrome/help/restart, defaultplayback, otherW6f andexactfamily UI debt remain
open. No visual layout change or recapture is needed under A0 if command parity
holds; any real change requires before/default/narrow inspection.

## Independent review clarifications

Restore commit/post-processing stays leaf-owned; no base wrapper merely dispatches
validate/apply. Validators iterate scalarFIELDS directly instead of building an
entire exported nested round just to enumerate keys. Mines release remains
physical-direction-only; physicalSpace+textF reveals, while Breakout follows its
text precedence. Tetris has no committedEnter binding. Preserve Pong tuplefallback
and all existing coercions/postrestore distinctions, including Tetris no-op audio
candidate, Mines no input/timestamp/frame reset and Pong no requestedframe.

Failed candidate construction may consume RNG; immutability scope is the live
model/app/input/frame/audio, not global randomness. Coercion before commit for a
raising custombool object is a separately tested edge repair if implemented;
ordinary JSON-valued accepted behavior must not tighten.

## Behavior lock and approved edge repair

Committed baseline27tests pass. Frozen evidence includes12880binding cases,
300actualMines input cases andall5numerical/export/render snapshots. Foreign
semantic bindings remain working-only ordered entries, not committed mappings.
A genuine prepare contract moves Pong/Mines sound coercion before live commit;
ordinary JSON coercions remain exact. A raisingcustombool atomicity regression
is a separately labeled repair, not a claim of arbitrary-object behavior parity.

## Verified outcome

Independent29candidate cases pass, with complete before/after contract equality:
12880bindings,300seededactualMines transitions andfivefullstate/render snapshots.
All111existing exactcandidate input/Qt/window/state/native cases pass. Source
constructors/render/advance are unchanged; allsixsourceRuff0, base typing clean.
RNG fixture correction is documented andallboardfields retained. The two custombool
atomicity repairs are explicitly separate from ordinaryJSON parity.
