---
type: PRD
prd: "91"
title: "PRD-91: Lumis Quest — the documentation is the world"
description: A top-down, gamepad-playable JRPG in ChiSurf's games hub where the documentation tree is the overworld, real fluorophores from spectra.db are the creature roster, combat is photophysics, and reviewing a page turns a wild room into a villager. Runs on chigame, a wgpu 2D engine mined from a reference render engine and reimplemented in-tree. Layers on top of the existing review_status.json sign-off system — does not replace it.
status: Draft
created: 2026-08-08
updated: 2026-08-11
owner: tpeulen
sibling: none
---

# Lumis Quest — the documentation is the world

# Where to pick this up

**Handover, 2026-08-11 (fourth pass).** The game was a walking simulator with a
type chart. It is now a game, and four things changed at the root:

1. **You fight animals, not dyes** (`api/bestiary.py`). A fluorophore is not an
   organism, so the thing in the grass is a **body** (23 real animals, each with
   vitality/power/**agility** and one behaviour of its own) with a **label** (a
   real fluorophore) fixed into it. The label supplies colour, damage, bleach
   rate and every feature -- each one a real property of the molecule
   (`bloom`/`slowburn` from quantum yield, `barrel` from a protein shell,
   `shiftwalk` from a wide Stokes shift, `nightsight` from far-red). **Tier is
   derived** from brightness against stamina, never assigned. Winning is
   **unbinding**: the label comes off, the animal walks away free, and it may
   choose to follow you -- so bodies and labels are collected *separately* and
   recombined in the PARTY tab. That split is the build game.
2. **Everything is data, run by an engine** (`api/engine.py`, `api/actions.py`,
   `api/context.py`, `data/*.json`). Dialogue is scenes of `say` / `say_from` /
   `choice` / `when` / `do` / `goto`; a story beat's completion rule is a
   condition expression; a consequence is a named action in a registry; anything
   the host must do (start a fight, cross manifolds, save) is a `Request` the
   runner queues. The `if role == "healer"` chain in the window class is gone.
   **A typo is loud** -- an unknown condition or action raises rather than
   silently never firing.
3. **The world is a 16-bit overworld** (`api/places.py`, `api/world.py`,
   `api/darkworld.py`). Biomes, lakes with sand rims, rivers that a road
   bridges, cliffs with a cave in them; settlements planned in *plots* so they
   have a middle -- hamlet / village / town, with a square, a well, a tavern, a
   supply house, a lens-grinder, a shrine, market stalls, lantern posts and
   garden beds, and a place name of their own. Five **Wardens** hold five seals
   (`api/tiers.py`); your licence caps what you may unbind and the wild scales
   to it. And there is a **dark manifold**: the same grid transformed by a
   lookup table (ash/tar/dead wood/ruins), entered through a cave and left
   through a rift, with Vesper's tower built into the middle of it.
4. **The town has a day** (`api/agents.py`). Townsfolk carry drives that rise on
   their own, walk to a real premises to spend them, and **start conversations
   when they meet**. Topics are weighted by the run (`mood_from`), so nobody
   gossips about the probe who takes labels off before there is one. The player
   overhears from a distance and can **drop into** the conversation. The loop is
   deterministic and offline; a configured model writes only the *words*, off
   the frame loop, with the authored exchange standing until it lands.

The story (`data/story.json`, `data/wardens.json`) is rewritten around **the
Marking**: Vesper the Lanternwright decided that if light will not stay in a
lamp, you fix it into something that cannot put it down. Thirteen beats across
five acts, and every beat's condition is a JSON expression.

**Defects only the screenshots and the new tests caught** (all fixed, do not
reintroduce):

* a Warden's seat was upgraded to a town **after** its compound had been
  measured, so the wall was painted at the old size and its `rect` said
  otherwise -- Iris walked straight through one. World building is now two
  passes: decide what every settlement *is*, then measure.
* `Runner._step` tested `"say"` before `"choice"`, so every step carrying both
  (the prompt above a menu) rendered as narration with its options silently
  dropped. Test `test_a_choice_branches_and_a_condition_hides_an_option`.
* `wild_beast` honoured `tier_cap` by walking down the *labels* only, so a heavy
  body over the cap stayed over it. It now walks down the bodies too.
* asking for wellspring ground was the one way to meet a crystal jelly in a
  field: the "never wild" filter fell back to the unfiltered list.
* four lantern glows at a tile and a half of additive light each turned a town
  square into a white hole. Only lamp posts glow now, at 0.85 tiles.
* the dialogue panel's last line sat under the bottom edge of the screen.

**Reproducing the gallery** (the rule is to *look*, and a screenshot nobody can
re-take is no evidence): `test/capture.py` writes all eleven screens --

```
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python \
    -m chisurf.plugins.misc.games.lumis_quest.test.capture \
    chisurf/plugins/misc/games/test/renders
```

**Handover, 2026-08-11 (fifth pass).** The arc is **finishable in play**.
`World.tower` now carries the door tile `darkworld.raise_tower` returns, and
`npcs.dark_population` stands **Vesper** at it -- her four screens and the
three doctrine replies were written, scripted and unreachable because nothing
was standing anywhere to say them. And the dark manifold has something to *do*:
**rekindling**, the exact inverse of unbinding. Give a shelved animal one of
your labels back and it comes up out of the ash with you -- it costs the
gentlest label you carry, on the grounds that you are choosing what something
else has to live with. `test_the_whole_arc_can_actually_be_walked` walks all
thirteen beats by doing each one rather than setting its flag, and asserts the
story ends.

Also: the dark manifold is drawn through a `DARK_WASH` multiplier, because the
trodden-earth floors and the roads kept their warmth and sat in the ash looking
like a different game. The roads stay visible on purpose -- "your own road,
under your feet, going the same way it always did" is in the lore.

**Mined from ZQuest Classic (2026-08-11).** 503,550 lines across 835 files;
`hero.cpp` alone is 33,462. The first pass through it read two files and came
back with one idea, which was not a survey. This is the survey. Checkout at
`junk/ZQuestClassic`; the four files read carry `CHISURF-REVIEWED` headers with
the per-file detail.

**Taken:**

1. **Per-quadrant solidity** (`core/combo.h`, the `walk` byte) -> `tiles.SOLIDITY`.
2. **The top-down z axis** (`zc/hero.cpp` ~8716) -> `overworld._airborne`.
   Height and *fall velocity* are the state; gravity accumulates into the
   velocity, the velocity comes off the height, landing is height reaching
   zero. Jumping is not a special case of walking, which is why it composes
   with everything else.
3. **Variable jump height** (`hero.cpp` ~8385, their `jump_loss`) -> `JUMP_CUT`.
   Release the button while rising and the jump is clamped short, so its
   height is a decision rather than a constant.
4. **The whole steering model** (`zc/guys.cpp` ~5829) -> `api/steering.py`.
   `enemy::newdir(rate, homing, special)` is three rules in priority order:
   divert to bait if hungry; else with probability `homing/256` turn toward the
   player **but only when `lined_up(8)` says you share a row or column** -- so
   enemies never beeline, they snap onto your axis and charge, which is the
   entire feel of a Zelda enemy; else a weighted random turn at `rate/16`,
   re-rolled up to 32 times against `canmove`. Taken with it:
   * **`homing < 0` means flee**, and `grumble < 0` means repelled by bait --
     one signed parameter serving drawn-to and afraid-of. This is the piece
     that matters most here, because it is where the bestiary stops being a
     stat table and takes a position: a marked animal did not choose to be
     labelled, so **flight is the default** (`temper_for`) and an aggressive
     trait is what turns it round. `AGGRESSIVE`, `LYING_IN_WAIT` and
     `PHOTOTACTIC` are read off real `bestiary.TRAITS` keys, with a guardrail
     test, because an invented key silently matches nothing and every animal
     quietly falls to the default.
   * **Decide at tile boundaries, walk exactly one tile** (`constant_walk`
     ~5959: `fix_coords(true)`, `newdir`, then a leg of `16/step`). This is
     the anti-wedge property and the answer to "get stuck on objects all the
     time": a creature is either grid-aligned or mid-leg, and a creature that
     cannot stop between tiles cannot come to rest inside one. Adapted to be
     dt-based -- a step that would overshoot is cut at the boundary and the
     surplus carried, so a hitched frame produces two decisions rather than a
     slide through a wall.
   * **The bait rule is light.** ZQuest's bait is an item; here the bait is a
     lamp post or **Iris herself** (`npcs._light_near`), which is what a probe
     is. One animal in the bestiary is phototactic and its entry already said
     so. Without her as a source the flag would do nothing at all across the
     map -- lamps stand inside town walls and wildlife may not go in -- and
     nothing would fail to report it.
5. **`fakez`** -> `steering.Drift.fake_z`, drawn via `npcs.Npc.lift`. A second
   height that is *visual only* and never touches collision, so a bob can be
   given to anything without re-auditing what it may now pass over. The
   shelved hover; the shadow stays on the ground and shrinks.

**Found and not taken -- the worklist:**

6. **`hoverclk`**: hover frames as a timer that suspends the fall. Distinct
   from `fakez`, which is what has landed: this one is a real suspension of
   gravity, i.e. a creature that can be *over* something.

**Skipped deliberately, with reasons**, so nobody re-derives them: the
eight-direction `newdir_8` (diagonals are exactly what stop grid-aligned legs
being grid-aligned), `place_on_axis` (an enemy that teleports into line is the
opposite of a creature whose position is always explicable), the `slide` /
`scored` / `stunclk` gating in the walk family (hit reaction belongs to action
combat; ours is turn-based photophysics and never happens on the overworld),
the rest of the walk family (the same `newdir` in different clocks), the combo
*type* system (`cWATER`, `cBRIDGE`, `dive_under_level` and ~200 more), which
encodes behaviour in the tile id and is why one byte grows into forty lines of
branching at `maps.cpp:2380-2480` -- Lumis Quest keeps behaviour in
`data/dialogue.json` against a tile and stays flat; the region/`rpos`
coordinate system, which exists to stitch screens into scrolling regions when
ours are a camera mode over one continuous grid; and `sideview_mode`, an entire
second gravity model for platformer rooms.

**Where to pick this up next**
1. **The interiors are built, tested, and unreachable.** `api/interiors.py`
   generates six kinds of room from ASCII maps under `data/rooms/`, every one
   sized to fit a single screen, with a door in the bottom wall row and
   standing spots for people -- and **nothing on the overworld opens one**. So
   "walkable houses, talk to people in houses" is still not true, and the room
   files are dead weight until it is. What is missing is small and specific: a
   door tile under a building that swaps the active grid the way `_cross`
   already swaps the dark manifold, and the arrival/leave positions. Measure it
   by walking into a house in `lumis_town`, not by `test_interiors.py`, which
   passes today and proves only that rooms can be built.
2. **A Warden fight is winnable by the strategy it exists to forbid.** Each
   Warden teaches one thing (`lesson` in `data/wardens.json`) and the fight is
   supposed to be unwinnable without it, but the only thing their tier changes
   today is which label they wear -- `_warden_beast` picks by
   `tier/5 * len(ranked)`. Tolm's boar should punish attacking every turn,
   Kestrel's Umbral owl should be *invisible* under the starting filter. The
   hook is `Battle(opponent_power=...)` plus a per-Warden rule; the lesson text
   is already written.
3. **The dark manifold has nothing to do in it.** `npcs.dark_population` places
   wraiths and the `wraith` scene sets the `the-shelved` flag, but there are no
   encounters, no reason to walk it, and no way to unbind anything down there.
   The obvious shape: a shelved beast you can *re-light* rather than unbind.
4. **The `LAB` and `RIG` tabs still speak the old vocabulary.** They culture and
   fit *labels*, which is right, but neither mentions bodies -- and the farm
   layer is the natural home for the bodies you befriend (feed, rest, a stable).
5. **`animal_*` and `beast_*` sprites are dead weight.** Every animal is now
   drawn per species and tinted by its label (`pixelart.creature_sprite`); the
   two generic drawings survive only as the `wraith` alias. Ten of the twelve
   body sprites are distinct; `serpent` and `crow` are the weakest and were
   judged acceptable from the contact sheet, not good.

---


**Handover, 2026-08-10 (third pass, same day).** On top of the
population-and-teaching pass below, the game now has a **front door and a
whole arc**: a title screen (Continue / New Journey / controls), a scripted
awakening in the Link's-Awakening register (wake in the grass with Bram the
last keeper over you; **Lumi is found dim in the world and joins you**, never
issued at the door), a doctrine act (clear `WORK_GOAL` rooms in your order's
own lands, counted from the pledge) ending in a per-order dawn epilogue, a
**16-bit art pass** (3-tone materials with outlines, lit vs dark windows,
grass/water variants chosen per tile, water animated by time, drop shadows
under every walker, pale town floors against dark walls), the **farm layer**
(LAB tab: cultures mature on a real-world clock spanning sessions; STALE
pages render as a distinct **WITHERED** state — doc rot visible as crop rot),
and **model-voiced NPCs**: `api/personas.py` builds a backstory per character
(keeper from their page, emissary from their doctrine, townsfolk from their
role), fetches through the same provider seam as questions, gates every reply
in code, caches per voice, and never blocks a frame — authored lines stand
until the voice is found in the background. Off by default behind the same
MODE-tab switch as questions; the scripted opening is never model-voiced.

**Traps from this pass:** the dialogue panel wraps at 46 chars — an authored
line over ~180 chars truncates even at 4 lines, so keep NPC lines short; the
chigame text path has no em-dash glyph (use `--`); and the shared `arm64` env
broke mid-session (self-referential tttrlib symlinks, see the board) — the
suite runs green via `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 … -p pytestqt.plugin`.

## What landed in the second session

1. ✅ **The in-world tutorial** (`api/tutorial.py`). Seven one-line banners in
   first-run order — walk → speak → enter a gate → stand on the recovery pad →
   face a beast → take a turn → answer the page — drawn in the reward gold at
   the bottom of the HUD. Every step completes **on game state** exactly as
   story beats do, latches once witnessed, and persists in the save
   (`RunState.tutorial`); a pre-tutorial save with cleared rooms skips the
   whole sequence. Banner text names keys via `{talk}`/`{confirm}` placeholders
   resolved from the **live** bindings, so it stays true after a scheme switch.
   *Trap:* the tutorial observes at the top of `update`, so a press is
   witnessed on the following frame — a test that taps and asserts must run
   one extra frame.
2. ✅ **The story cast** (`npcs._story_cast`). Merel (Rigour, The Great
   Library), Halden (Clarity, The Pilgrim Road), Sable (Discovery, the
   references/Cairns land, preferring an "The Unlinked" village) — fixed
   positions outside a gate, doctrine-coloured halo and tint, four screens of
   dialogue composed from `story.ORDERS`. **`story.choose` is wired to
   talking**: the dialogue ends in "Will you serve …?", Confirm pledges,
   Cancel walks away with the choice open. Before this there was *no* path to
   choose an order in play at all — only the save-restore path called
   `choose()`. Also one named **recovery warden** per clinic. `Npc` grew
   `lines: tuple[str, ...]` and `role: str` (dispatch on role, not callbacks —
   it serialises and tests cleanly).
3. ✅ **Villages are towns** (`ROOM_PITCH = 3`, `VILLAGE_MARGIN = 2` in
   `api/world.py`, formula `(n-1)*pitch + 2*(1+margin) + 1`). Streets are two
   tiles, a perimeter street rings the walls, and **townsfolk** (smith, child,
   gatekeeper…) scale with compound area (`interior // 48`, cap 5), not with
   review state — an all-wild village still has people in it. Keepers stay
   one-per-settled-page. Measured after: world 368x282 = 103,776 tiles
   (was 76,320), **build 0.31 s**, **median frame 3.3–4.4 ms (~230–305 fps)**
   at 960x540 inside the largest compound.

**Three defects only the screenshots caught** (all fixed, do not reintroduce):

- **Bottom-band draw order.** The story beat, tutorial banner and loot line are
  drawn along the bottom; the dialogue panel is 0.97-alpha and sat *after* them
  in `_draw_hud`, so they bled through as ghost text behind whoever was
  talking. Dialogue now owns the bottom band outright — panel first, return.
- **Dialogue wrapped to 2 lines cut the orders' beliefs mid-sentence.** The
  panel takes 3 lines now and grew to fit.
- **A beast spawned inside a village compound** — `_open_spot` accepted any
  walkable tile and FLOOR qualifies. Wildlife placement and beast wandering now
  use `WILD_GROUND` (grass/road only), because "inside the walls nothing fights
  you" is the one safety rule the map teaches.

## The open fronts, in the order they matter

1. **Offline keeper dialogue is still canned** (Part 3 wants it from the page:
   summary line + "did you know" trivia, cached under the page `sha256`). The
   model voices cover this *when the model is on*; the deterministic fallback
   still speaks from the shared greeting bank. `Npc.lines` is the surface.
2. **The five new mini-games** (Part 7) and the **lore OKF bundle** (Part 8)
   from phase 6 do not exist. The mini-games matter more now that voices can
   be model-fetched — they are the designed latency cover.
3. **Phase 7's network half** is unbuilt (the farm half landed: LAB cultures +
   withered plots). The ZMQ trap stands: REQ/REP is lock-step, live positions
   go over PUB.
4. **No gamepad backend exists**, so "gamepad-playable" is still untested on a
   gamepad; and the shipped question generator tests *attention* rather than
   understanding (the model-backed provider is wired, opt-in, off by default).

## What is already done, and where the traps are

1. ✅ **Phases 1 and 2 done.** The engine is in `chisurf/gui/chigame/` and **all
   five arcade games run on it**, off `QPainter`, each verified against a
   before/after screenshot pair. The engine record is
   [chigame](../subsystems/chigame.md) — read it before touching rendering, and
   read its "what the ports taught" list before laying out a new screen.
2. ✅ **Phase 3 done — a real, huge, pixel-art overworld you can walk.**
   **318 x 240 = 76,320 tiles** (5724 x 4320 world units) of painted terrain:
   grass, woodland, rock, water you cannot cross without a bridge, roads gate to
   gate, and villages that are **walled compounds with a gate**. Iris and Lumi
   are 16x16 sprites with facings and a two-frame walk cycle. Collision is real
   and pinned by tests. Measured: **1.3 ms/frame (795 fps)**; the world builds in
   ~0.9 s. See Part 11b for the cast and the art.
2b. ✅ **Older note — the overworld's first form.** `api/world.py`
   derives it from the docs' own toctrees and the review sidecars;
   `gui/overworld.py` draws it and walks Iris (with Lumi trailing) around it.
   **Measured against the real corpus: 7 regions, 47 villages, 377 rooms — 269
   wild, 78 scouted, 30 settled** — built in ~340 ms, positions deterministic.
   The map covers every non-index page (asserted per section), and there are
   currently **no orphans**: the "Unlinked" village exists as a guard for a
   future one, not because the corpus has any today.
3. ✅ **Phase 4 landed — combat, and it is photophysics.** `api/roster.py` reads
   **472 creatures** from `spectra.db` (366 fully measured); `api/battle.py` is
   the turn-based fight; encounters trigger from the overworld and the battle
   screen is drawn over it. Measured: a 520 nm donor is **x0.50** against a
   blue absorber and **x2.00** against one absorbing at 567 nm -- the type
   chart is the real overlap integral, not a designed table. Still **no AI**,
   deliberately.
   ✅ **Gear, loot and healing landed too.** `api/gear.py` reads **673 real
   optical parts** from the same database (333 emission filters, 172 dichroics,
   100 excitation, 68 detectors), each with its measured transmission curve. A
   filter is not "+3 damage": it decides **what you can see**. Fitted optics
   multiply your shot by what they pass, and a creature the filter blocks is
   **not drawn on the map at all** -- so re-walking cleared ground with different
   optics shows you what was always there. Loot is seeded by the page (no
   farming for rerolls) and a remoter room yields a **narrower**, more selective
   filter: better in its band, useless outside it. **FRAP is a place**: a
   recovery station just inside every village gate, because photon budgets
   persist between fights and attrition is where the difficulty lives.
   ✅ **Catching and persistence landed.** Collecting a creature is a menu
   action whose odds come from two real things: how far into its dark state you
   have driven it, and **whether the fitted filter can see it at all** -- you
   cannot collect what you cannot detect. A run persists to
   `~/.chisurf/lumis_quest_run.json`, stored **by identifier rather than by
   value**, so a corrected extinction coefficient in the database reaches a
   saved game instead of the save freezing a number that has since been fixed.
4. ✅ **Phase 5, the review bridge — the game touches the docs now.** Beating a
   guardian is spectroscopy and says nothing about whether anyone read the
   page, so **clearing a room asks the page its own question**. In *expert*
   mode a correct answer calls `review.set_status(..., reviewer_kind="human")`;
   in *training* mode nothing is ever signed off. The guards are the review
   system's own: a wrong answer signs nothing, no challenge signs nothing, an
   **edit mid-encounter is refused on the content hash**, and an untracked page
   is refused outright.
   Questions are **span-grounded and keyed by the page's `sha256`** — the same
   hash the sidecar stores — so an encounter is reproducible, self-invalidating
   and testable with no model. **79 of 80 sampled pages are questionable.**
   The generator here is deterministic and model-free: it blanks a distinctive
   term out of the page's own prose. It tests attention rather than
   understanding, which is **weaker than the design intends** — a model-backed
   provider drops in behind the same grounding check, and the check is the part
   that matters.
5. ✅ **Crafting landed, and it runs through the existing simulator.** `api/rig.py`
   assembles an excitation filter, dichroic, emission filter and detector into a
   path. Its **Förster radius comes from the light-path simulator's own
   `calculate_r0`** rather than being re-derived, so a crafted rig and a real
   instrument description cannot disagree about the physics. Measured on the
   shipped catalogue: a rig tuned to 610 nm collects its acceptor at 0.145 and a
   519 nm donor at 0.012, giving **8.2% bleedthrough**, with **R0 = 55.7 A** --
   all realistic numbers.
   ✅ **The crafting screen landed too**, and it forced a better shape: nine
   actions is the whole controller and the overworld had spent all of them, so
   every extra screen lives behind **one pause menu with tabs** -- MAP, RIG,
   PARTY, MODE -- which is the convention this kind of game uses anyway. The
   RIG tab fits found parts into their own slots and shows the assembled path's
   live response; PARTY swaps a collected creature into the party; MODE is the
   one switch that decides whether anything is signed off.
6. ✅ **The AI layer and the findings flow landed — PRD complete.** Three
   interchangeable question providers (deterministic, agent, recorded) all pass
   the **same** grounding gate: a challenge whose quoted span is not in the page
   is discarded and counted. Encounters cache under the page `sha256`. The model
   is **off by default** and opt-in from the MODE tab, because a configured
   provider would otherwise put a network call in the middle of every first
   encounter.
   Expert mode's other half is **flagging**: pick the sentence at fault with the
   pad, then one of eight fixed categories. No typing, and the record is
   machine-checkable rather than prose. Findings pool in the per-user directory
   — **nothing is ever written into `docs/`**, because this is a shared working
   tree — and export refuses any finding whose page has changed since it was
   made.
7. ✅ **The tutorial, the story cast and the village rework** — see "What
   landed this session" above. `gui/tool.py` is no longer the first draft's
   XP panel; it hosts the overworld and its free-text field is gone.

**Traps already identified, do not rediscover them:**

- `spectra.db`'s `optical_properties` is an **EAV table** — `property_name` /
  `property_value`, values stored as **text**. `qy` ranges "0.0" to "1",
  `ext_coeff` "1" to "99000"; a naive float cast over the whole table hits
  `Origin` and `Material Name` and raises. Filter by `property_name` first,
  and expect missing stats: only 725 of 2288 probes have `ext_coeff` and 672
  have `qy`, so a creature's stat block must degrade rather than assume.
- **`review_status.json` is per-directory, not global**, and only two exist
  today (`docs/manual/` 79 entries, `docs/concepts/` 19). The other ~288 pages
  have **no entry at all** — absent is not "not reviewed", it is "never
  touched", and the map's fog depends on telling those apart.
- **`rendercanvas.qt` raises on import** unless a Qt binding is imported first.
  `import PyQt5.QtWidgets` (or `qtpy`) must precede it, or the engine fails at
  import time with a message that reads like a missing dependency.
- Under `QT_QPA_PLATFORM=offscreen` a `QRenderWidget` yields a
  `WgpuContextToBitmap` context rather than a surface context. That is the
  correct path for headless capture, but it is **not** the same code path as a
  real window — a screenshot test proves the scene, not the swapchain.
- **Layout must be anchored to the *nominal* grid, not to where rooms land.**
  Regions were re-anchored to their rooms' bounding box, so adding one page
  whose jitter lowered the minimum slid the entire region — the "a new page is
  a new building, not a reshuffle" property silently failed. A test pins it.
- **Village pitch must follow village height.** A 30-room village is six rows
  of rooms (264 units) against a 260-unit fixed spacing, so villages sat on top
  of each other in the map view.
- **The mean room position is not the centre of the world.** `reference` holds
  145 of the 377 rooms, so averaging drags a fit-to-world view into it and
  clips everything else; use the bounding box.
- **The temp-index commit recipe makes your working copy drift.** Committing via
  a temporary `GIT_INDEX_FILE` (HEAD + only your hunks) is the right way not to
  steal another instance's staged work, but it rebases onto HEAD each time while
  the on-disk file keeps accumulating separately. `okf/log.md` fell **10 entries
  behind** and `okf/references/known-issues.md` **6**. Worse, the *main* index
  goes stale against the new HEAD, so files you have just committed show as
  **staged deletions** — and anyone committing that index would delete them.
  After every such commit: `git reset -- <your paths>`, and diff your working
  copy of any shared file against HEAD.
- **REQ/REP is lock-step.** The existing `ZmqServer` (`chisurf/server/transport/zmq.py`)
  pairs REP with PUB. Many clients on one REP socket serialise, which is fine
  for turn-based play and trading and wrong for live avatar positions. Those go
  over PUB, or REP becomes ROUTER/DEALER.

---

## Summary

Nobody enjoys reading documentation to approve it. ChiSurf's existing review
gate ([`help/api/review.py`](../../chisurf/plugins/core/help/api/review.py),
per-directory `review_status.json`, `csc help review-check`) tracks **whether** a
page was signed off — but the experience is a thankless `return True`. The
sign-off queue sits stale, the release gate stays blocked, the docs drift.

**Lumis Quest** is a top-down JRPG in the games hub in which the documentation
tree *is* the overworld. You are **Iris** (renameable). Your companion is
**Lumi**, a glowing dye-sprite whose colour is your starter fluorophore's real
emission wavelength. You walk a world generated from the docs' own toctrees,
clear wild rooms, and every page you genuinely review becomes a **villager** who
lives there and talks about their own content. The world visibly populates as
the corpus gets tended.

It is not "points and badges on a boring task" — that is the pointsification
trap and the research is clear that it backfires. Nor is it a quiz with a health
bar, which is what the first draft of this PRD amounted to. The fun is carried by
**systems built out of real photophysics**, all of which work with the AI
switched off:

- **Photobleaching is HP.** A high-quantum-yield dye hits hard and burns down fast.
- **Spectral overlap is the type chart** — 455 real creatures, a matchup table
  computed from shipped spectra rather than invented.
- **Crosstalk is friendly fire.** The wrong emission filter and your own team's
  light hits you.
- **FRET is a two-dye combo**, its reach the real Förster radius.
- **Triplet state stuns. Blinking flinches. Quenchers debuff. Photostability is defence.**
- **FRAP** — Fluorescence Recovery After Photobleaching — is the healer. The
  Pokémon Center is a real technique.

The AI sits *on top* of that, never inside the inner loop: land a genuine flaw in
a page and it is a critical hit.

## What changed from the first draft, and why

The 2026-08-08 draft specified a flat quest list plus a **text-based, AI-narrated
dungeon** (its Part 13). Both are superseded.

| First draft | Now | Why |
|---|---|---|
| Text dungeon, ASCII room tree | Top-down tile world on a GPU engine | A text dungeon is a reading task wearing a costume. The ask was a game. |
| Beasts by page difficulty (slime/goblin/troll/dragon) | 455 real fluorophores from `spectra.db` | The roster already exists, with real stats, and playing it teaches spectroscopy. |
| Review = attack, approve = damage | Spectral tactics; the AI challenge is a **critical hit** | Combat resolved by quiz answers is an exam repeated 386 times, and every turn stalls on a model. |
| XP/streaks as the compulsion loop | **Loot and build expression** as the loop | The draft's own research section warns that points on an unfun activity backfire. Gear that changes what you can *perceive* is a reason to walk back through a cleared region. |
| One mode | **Training** and **Expert** | Learning fluorescence and clearing review debt are different jobs and must not grant the same thing. |
| Solo, team progress bars deferred | Git-synced shared world + live ZMQ presence + a farm | Asked for explicitly. |
| Free-text suggestions | **No text entry at all** | Gamepad-playable. This forces structured review data, which is better than prose anyway. |

What **survives** from the draft, because it was right: flow-sized sessions
(3–15 min), variable reward schedules, progress visualisation (the Zeigarnik
effect), streak protection with grace days, cooperation over leaderboards, the
quality-discovery mechanic, "did you know" trivia, and the hard rule that **AI
cannot grant human sign-off**.

## Non-goals

- **Replacing `review.py`.** The game calls `set_status()` underneath; the gate
  reads `review_status.json` as before.
- **An online leaderboard.** Cooperation, not ranking.
- **Mandatory participation.** Opt-in. Coerced gamification backfires at 60–90 days.
- **Gamifying code review.** Documentation only.
- **Shipping art or music binaries.** Everything is generated (see Parts 11–12).

---

## Part 0b — the premise, and how a run opens

**Everything alive in this world carries light.** A person, a hound, a thing in
the long grass — each holds a quantum of it, spends it, and gives back what is
left, changed. That is not a metaphor over the mechanics; it *is* them: a
creature's brightness is how hard it strikes, emitting spends it, and one driven
dark can be carried home. Knowledge is the same substance — a page somebody
read and vouched for **burns**, with its keeper at the door; one nobody opened
goes dark, and something moves into the dark.

**The Fading** is that premise's consequence: light is leaving, a lamp at a
time, until a land is quiet and nobody recalls it was otherwise. **Iris** is a
probe — a quantum given a body, sent to find where it goes, and spent doing it.
**Lumi** is a hound of light who can smell where light has been.

The three orders (Part 8) disagree about what the Fading *is*: Rigour says the
light is going because too much of it lies; Clarity says the light is fine and
the doors have closed; Discovery says the worst dark was never lit at all.

A fresh run opens on five cards of this before the world appears, so a player
arrives knowing what they are looking at. **A resumed run skips it** — a run
already played does not need telling.

## Part 1 — two modes

The game has two modes over one world, one save and one engine.

| | **Training** | **Expert** |
|---|---|---|
| Purpose | Learn fluorescence | Clear review debt |
| Earns | XP, dyes, gear, gold | All of that, plus real doc improvement |
| Touches `review_status.json` | **Never** | Yes — `reviewer_kind: human` on a win |
| Flagging interface | **Multiple choice** (JRPG): the AI offers candidate flaws, you pick the real one | **D-pad span cursor**: move over the page's spans, select the offending one, then choose a defect category |
| Produces edits | No | Yes — hunks pooled for the spoils flow (Part 14) |

The split is what keeps the existing sign-off rule honest: **a player learning
fluorescence has not reviewed anything.** Training mode teaches you to *recognise*
a defect from options; expert mode makes you *find* one unaided.

Defect categories (expert mode, a fixed pad-selectable list): undefined symbol,
wrong units, missing citation, contradicts another page, stale screenshot, dead
link, unstated assumption, notation disagrees with the code. The AI turns
`(span, category)` into two or three drafted comments and you pick one with A.
The recorded artifact is structured and machine-checkable — something free prose
never gives.

## Part 2 — the world is the corpus

The overworld is generated from the docs' own **toctrees**, not from the
filesystem — the help plugin already parses them into a grouped, reading-order
tree (`help/test/test_toc.py`, `test_widgets.py`), and that is the curated
structure a human authored.

**Corpus as of 2026-08-10**: 386 pages — `reference/` 146, `manual/` 79,
`guides/` 69, `concepts/` 44, `development/` 31, `fundamentals/` 13.

- **Region** = a top-level docs directory. Six of them, each an authored biome
  template: tileset rules, palette, music context, prop rules.
- **Village** = a toctree group or subdirectory. Its **prosperity** is the
  fraction of its pages reviewed; a neglected section is visibly a ghost town.
- **Room** = a page. Wild until cleared.

Layout inside a region is procedural, **seeded by the page's path**, so a page
keeps its location as the corpus churns. A new page appears as a new building; a
deleted page leaves a ruin. Nothing about the map is hand-placed, because 386
hand-placements is a second full-time backlog that goes stale on the next commit.

### Hiddenness is review debt × depth

The exploration reward gradient is pointed at exactly what the project needs:

- Pages with **no `review_status.json` entry at all** (~288 today) sit furthest
  off the path and pay most.
- The **deeper and less-linked** a page is in the toctree, the more remote its
  room.
- The 98 pages currently at `ai-reviewed` (79 `manual/`, 19 `concepts/`, all
  `reviewer_kind: ai`, dated 2026-08-06) are the **expert-mode frontier** — the
  AI has been there, no human has.

Absent, `ai-reviewed`, and `human-reviewed` are three different fog states and
must be rendered as three different things.

## Part 3 — villages and villagers

**Reviewing a page turns a wild room into a villager.** This is the progress bar
made into a place, and it is the single strongest visual reward in the design.

- A villager's **dialogue comes from their own page** — its summary line and the
  "did you know" trivia — generated once and cached under the page `sha256`.
- A village's **prosperity** is its reviewed fraction: buildings light up,
  villagers appear, the music context brightens.
- When a page's `sha256` moves, its villager goes **quiet and the plot withers**
  (Part 10). Doc rot is visible from across the map.

Authored NPCs on top of the derived ones: the three mentors (Part 8), gear
vendors, and the **FRAP clinic** where photobleached dyes recover.

## Part 4 — the roster: `spectra.db` is already a Pokédex

`chisurf/plugins/spectra_downloader/spectra.db` ships, today:

| | count | becomes |
|---|---|---|
| probes | 2288 across 33 types | — |
| FPBase fluorescent proteins + organic dyes (Atto, PhotochemCAD) | ~455 | **creatures** |
| Chroma / Thorlabs / 3Doptix filters, dichroics, mirrors, ND, notch | 449 | **gear** |
| APD detectors, light sources | — | **gear** |
| `optical_properties` rows | 19882 | **stats** |
| spectra (903 emission, 825 absorption, 850 transmission, 245 excitation) | 2896 | **the type chart** |

Stat mapping — every number real, none invented:

| Game stat | Source |
|---|---|
| Attack | brightness = `ext_coeff` × `qy` |
| HP | photostability (photobleaching quantum yield where known, else a class default) |
| Type | `em_max` / `abs_max` band |
| Effectiveness vs. target | **spectral overlap integral** of your emission with its absorption |
| Combo reach | Förster radius via the existing `calculate_r0` |
| Colour | `em_max` → sRGB (Part 12) |

**Degrade, never fabricate.** Only 725 probes carry `ext_coeff` and 672 carry
`qy`. A creature missing a stat shows it as unknown and gets a class default in
combat, and its Pokédex entry says so. A game that invents a quantum yield is
teaching a false fact.

## Part 5 — combat is photophysics

Turn-based, JRPG command menu, gamepad-only. Turn-based because a model in the
loop cannot be hidden behind real-time combat — and because reading a page and
fighting must coexist.

Core loop: pick the dye whose emission overlaps the opponent's absorption, manage
photobleaching, avoid crosstalk, chain FRET combos, swap gear. **All of this runs
at full speed with no AI configured.**

The AI layer adds the **critical hit**: answer its challenge (training: multiple
choice; expert: find and categorise a real flaw) and the fight ends early. Skipping
it costs you tempo, not the game.

Preserved from the first draft, because it was the best idea in it: **an expert
page cannot be cleared by rubber-stamping.** The hardest opponents require a
genuine flag, not a clean approve.

## Part 6 — crafting: rigs, and building the world

Two crafting layers.

**Rigs.** Wire collected lasers, dichroics, excitation and emission filters,
detectors and dyes into an optical path — through the **existing**
[`lightpath_simulator`](../../chisurf/plugins/core/lightpath_simulator/) node
graph, whose `OpticalPathSimulator.propagate_node` and `calculate_r0` already
compute crosstalk and Förster radii from `spectra.db`, with a headless CLI, an
RPC method and mmCIF instrument export. A crafted rig's stats are therefore
*computed*, and a bad filter choice **genuinely blinds you** to creatures that
are there. That is the engine of the loot loop.

**The world.** In expert mode you also build the map: raise a new page where the
toctree has a gap, place signposts that are real cross-links. You construct the
documentation you review.

## Part 7 — mini-games

**Five new mini-games**, designed for this game rather than retro-fitted. (The
five ported classics stay what they are: engine stress tests on the games ribbon.)

They do three jobs at once:

1. **Skill checks replacing dice** — a special move is a mini-game you must
   actually play, so the outcome is earned rather than rolled.
2. **The crafting activity itself** — aligning a rig, packing emission bands into
   detection channels where overlap *is* crosstalk damage.
3. **Cover for model latency** — whenever the AI is generating, a mini-game fills
   the wait. The model's latency is never felt as a stall.

Job 3 is the one that makes the AI tolerable in a real-time-feeling game, and it
is why mini-games are not optional flavour.

## Part 8 — mentors, story, and the win condition

Three orders quarrel over what knowledge should be:

| Order | Doctrine | A critical hit is… | Victory |
|---|---|---|---|
| **Rigour** | Derivations, citations, exact symbols | An unstated assumption, a wrong unit, a missing citation | Every derivation page cleared |
| **Clarity** | A newcomer arrives in five minutes | A term used before it is defined, an unexplained jump | Every entry-point page cleared |
| **Discovery** | The unwritten found and mapped | An orphan, a dead link, a gap in the tree | Every unlinked and never-reviewed page found |

Your mentor **grades your battles** and **styles your edits** — the doctrine is
mechanical, not flavour text. Choice is **per-run, switchable at a cost**
(forfeits standing and some routes).

**The win condition is your mentor's doctrine satisfied, not 386/386.** A run is
finishable in a humane number of sessions; three runs cover the corpus from three
angles; the release gate genuinely benefits. Requiring every page would recreate
the unbounded task this PRD exists to break.

Story text is **AI-drafted, human-edited, committed**: a fixed spine of mentors,
act beats, branch points and boss encounters. The 386-page bulk is never
hand-authored.

### The story generator's memory is its own OKF bundle

`lumis_quest/lore/` is an **OKF bundle** in the same format as `okf/` itself —
`index.md` plus `characters/`, `factions/`, `regions/`, `bestiary/`, `beats/`,
each a concept with YAML frontmatter and `[[links]]`.

The generator **reads it for continuity and appends new canon to it**. This gives
story memory across sessions with no vector database, no embeddings and no new
dependency — progressive disclosure is exactly what the format is for, and it is
reviewable as a diff, which a vector store is not.

## Part 9 — the AI layer

**Closed-book, span-grounded, cached by page `sha256`.** An encounter — questions,
claims, beast framing, loot table — is generated once from the page alone; every
AI claim must quote a span verified to exist in the source; the whole thing is
cached under the page's `sha256`, the hash `review_status.json` already keeps. So
encounters are reproducible, headlessly testable, reviewable as data, and
**self-invalidating when the page changes** — the same rule that already
downgrades a stale review.

This directly answers failure modes already observed from a live model against
this corpus: fabricated citations, answering from excerpts, and "correcting" the
user's own terminology.

**The AI is required to play.** No provider configured (`chisurf/core/agent/`
supports OpenAI, Mistral, OpenRouter, Ollama, LM Studio, custom) means the game is
disabled. *Accepted risk, recorded in "Open risks".*

**Tests never call a model.** A fake provider replays recorded transcripts, so
every battle, edit-proposal and grading path is deterministic with no key and no
network. Real-model runs stay behind an opt-in marker.

## Part 10 — the farm, and the network

### Two farms

**Your lab.** Dyes are *cultured*, not only caught: a sample expressing a
fluorescent protein matures on a real-world clock, because **FP maturation
genuinely takes minutes to hours** — the growth timer is a real physical property,
not an invented wait. Harvest brightness, gift rare dyes, visit a colleague's bench.

**The docs as shared garden.** A page is a plot. When its `sha256` moves, the plot
**withers** and needs re-tending. The nagging mechanic points precisely at the
project's real problem: doc rot is crop rot.

### Network

Two transports, deliberately:

- **Durable shared world = git.** `review_status.json` is already committed, so
  who cleared what syncs on `pull`, with the team's existing conflict handling, no
  server, no accounts, no sync protocol.
- **Ephemeral layer = the existing ZMQ REP/PUB** (`chisurf/server/transport/zmq.py`,
  with `EventBus` topics and `SessionState`): presence, trades, gifts, visiting.

If nobody runs a server you still see colleagues' territory after a pull. The
server only adds the live layer. **Trap**: REQ/REP is lock-step — live positions
must go over PUB, or REP becomes ROUTER/DEALER.

## Part 11 — audio

Context-dependent music: **overworld, town, battle, underworld, victory**, with
crossfade on `audio.set_context(...)`.

Zero binary assets, following the pattern already in the tree: the existing
`pong/sound.py`, `breakout/sound.py`, `tetris/sound.py` each **synthesise WAV
programmatically** (`math`/`struct`/`wave`) and play through `QSoundEffect`. Those
three near-duplicates consolidate into chigame as a small chiptune sequencer —
waveform generators plus ADSR, a track as JSON note data, synthesised once at load.

**Music ships inside the AssetPack** (Part 12), so swapping the pack swaps the
soundtrack along with the art.

## Part 11b — the cast: Iris, Lumi, and the pixel-art look

**Iris and Lumi are photons, and they are shared across the whole games hub**
(`chisurf/plugins/misc/games/characters.py`). The same two characters are the
ball in Pong, the probe in Breakout and the pair who walk Lumis Quest. That
works because a photon is the one thing which legitimately appears in a detector
array, a spectrometer, a lifetime measurement *and* a walk across a map — so one
cast spans the hub without the conceit straining. A character who exists in only
one game is a mascot; a character you meet again somewhere else is a character.

- **Iris** is the probe: the quantum you send in and follow. She is drawn as a
  proper character rather than a marker — **a glowing photon core for a body**,
  with head, hair, face, arms, legs, boots and **a sword**. Her colour is her
  current wavelength, so when something re-emits her she changes; that is not a
  costume change, it is what happened to her. 488 nm to start, because it is a
  real laser line and bright enough to follow on a dark field.
- **Lumi** is the companion, and **Lumi is a dog** — four legs, ears, snout,
  tail, the same glow, trotting after Iris. Green at 520 nm, and never
  re-emitted, so Lumi is the constant a player orients by while Iris changes.

### The art is 16-bit pixel art, authored as string art

The look is SNES-era pixel art, not flat colour. Two decisions make that
possible without shipping binaries:

1. **The engine grew a sprite path.** `chigame` has an RGBA sprite atlas on its
   own binding with a **nearest-neighbour sampler** and hard alpha — pixel art
   that is linearly interpolated is not pixel art, and a soft edge puts a halo
   around every sprite against the tile behind it. This is also the second
   `AssetPack`-shaped consumer, which is what finally makes "the look is
   swappable" a demonstration rather than an argument.
2. **Sprites are string art in the source** — one character per pixel, one row
   per line, in `lumis_quest/gui/pixelart.py`. A PNG in the tree is opaque:
   nobody can see in a diff that a sprite changed, let alone how. This way
   changing Iris' sword is changing two characters on one line, and the guard
   tests can assert things a binary cannot expose — that no sprite is short a
   row, that every pixel names a defined colour, that her back view has no eyes
   while her hands still show, that Lumi has separated legs, and that the second
   walk frame actually differs from the first.

Terrain is dithered rather than flat (a single flat colour per tile is exactly
what makes generated art look generated), and each material carries a light and
a dark tone so it reads as form. Facings are drawn three times, not four: the
left view is the right view with its uv rectangle reversed.

## Part 12 — look, and swapping it

**No image assets.** Terrain, buildings, villagers and creatures are drawn as
signed-distance shapes in WGSL. A creature's colour comes from its **real
emission maximum** via wavelength→sRGB, and its aura is shaped by its **real
emission spectrum** — a dye looks like what it looks like down a microscope. Zero
licensing, tiny repo, and the art itself teaches spectra.

**The look must be swappable.** Games never reference art directly. They emit
*semantic* draw calls — `draw("dye", "atto488", state="idle", at=...)` — and an
**`AssetPack`** resolves them. The default `ProceduralPack` renders SDFs; an
`AtlasPack` backed by a sprite sheet can drop in later **without touching a line
of game code**. A pack declares its tiles, palette, sprite mappings, shaders and
music in one manifest. Specified in [chigame](../subsystems/chigame.md).

## Part 13 — input: nine actions, no text

Gamepad-playable, therefore **no heavy text entry anywhere**. chigame exposes an
abstract nine-action controller — four directions, Confirm, Cancel, Menu, two
shoulders — and every game and every UI is written against it. That constraint by
itself enforces the no-text discipline from day one and makes input tests trivial
to drive headlessly.

Keyboard bindings ship first; a real pad backend slots in behind the same seam
later, without touching a game. Nothing gamepad-capable is currently installed
(no `QtGamepad` in this Qt5 build, and Qt6 removed the module), so the dependency
decision stays deliberately open.

Name entry (Iris is renameable) uses a **pad-driven character grid**, the JRPG
convention — not a text field.

## Part 14 — state, saves, and the spoils flow

Save state stays where it is: `~/.chisurf/lumis_quest.json`, per-user, outside the
repo. The schema carries a **reviewer identity**, so the team view (Part 10) is a
later read-only feature rather than a rewrite.

**Edits never write during play.** Accepted hunks pool in `~/.chisurf`. An
explicit "claim the spoils" action applies them, and **refuses any hunk whose page
`sha256` has moved** since the encounter was generated. This is not optional
polish: this repo is a shared working tree in which several agents and the user
hold uncommitted edits in parallel, and a game that writes to `docs/` under them
would silently destroy work. A stale hunk fails loudly instead.

## Part 15 — what carries over from the first draft

Kept, essentially unchanged, and folded into the above:

- **Variable rewards** — XP per clear randomised in a band, with rare high payouts.
- **Flow sessions** — a session is 3–15 minutes, with a clear start and a completion.
- **Progress visualisation** — personal, village and corpus bars; never a blank slate.
- **Streak protection** — grace days for streaks past 14 days, because the
  asymmetric loss of a long streak causes disengagement.
- **Cooperation over competition** — shared progress, no leaderboards.
- **Quality discovery** — finding a real problem is the highest-value act.
- **"Did you know?" trivia** — now villager dialogue.
- **AI cannot grant human sign-off** — now enforced by the mode split.

---

## Phasing

Engine-first, proven by the ports. Nothing is built speculatively, and **phases
1–4 are a fun game with no AI in them at all** — which is the natural place to
stop if this stalls.

| Phase | Delivers | Proves |
|---|---|---|
| 1 ✅ | `chigame` + **pong** | Engine seam, InputMap, audio, offscreen capture |
| 2 ✅ | **breakout, tetris, minesweeper, number_quest** | Batching, grid+text, picking, menus |
| 3 ✅ | Overworld from the toctree, villages, fog | Map generation, walking, camera |
| 4 | Combat, roster, gear, loot | The game is fun without a model |
| 5 | AI layer, both flagging interfaces, spoils flow | Grounding, safety |
| 6 | Crafting, five mini-games, factions, story, lore bundle | Depth |
| 7 | Farm timers, git-synced territory, live presence | Social |

## Definition of done (Phase 1)

- [ ] `chisurf/gui/chigame/` exists with scene, camera, sprite/SDF batcher,
      `InputMap`, `AssetPack`, audio, offscreen capture
- [ ] `pong` runs on it inside a ChiSurf dock, off `QPainter`
- [ ] A headless PNG has been rendered **and looked at**
- [ ] `wgpu` + `rendercanvas` declared in `pixi.toml` and `pyproject.toml`
- [ ] Reference checkout annotated in `junk/` (header-only, zero deletions)
- [ ] [chigame](../subsystems/chigame.md) written; `okf/log.md` appended

## Open risks

1. **AI required to play** (Part 9). A first-time user with no provider gets a
   disabled game. The fix, if this bites, is pre-generated encounters shipped as
   data — which would make training mode playable offline. Deliberately not done.
2. **Scope.** Seven phases. Mitigated by the ordering: each phase ships something
   playable, and the AI-free game arrives at Phase 4.
3. **Renderer path divergence** — offscreen capture uses a bitmap context, not the
   swapchain, so screenshots prove the scene and not presentation.

## Decision record

Settled 2026-08-10: two modes; tile world replaces the text dungeon; spectral
tactics as combat core with the AI as critical hit; loot/build as the compulsion
loop; procedural map from toctree seeded by path; hiddenness = review debt × depth;
mentor factions Rigour/Clarity/Discovery, per-run switchable; win = doctrine
satisfied; `spectra.db` as roster and gear; crafting via lightpath + world-building;
five new mini-games doing skill-checks/crafting/latency-cover; closed-book
span-grounded encounters cached by `sha256`; AI required, tests on recorded
transcripts; expert-only sign-off; spoils patch flow with hash refusal; git +
ZMQ split; two farms; villages from toctree groups, villagers from reviewed pages;
procedural WGSL art with swappable `AssetPack`; synthesised context-dependent
music inside the pack; nine-action InputMap, no text entry; lore as an OKF bundle;
named **Lumis Quest**, hero **Iris**, companion **Lumi**, engine **chigame**.
