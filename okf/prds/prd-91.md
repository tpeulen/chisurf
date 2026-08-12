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

**Handover, 2026-08-12 (settings became data; the game became an easter egg).**
*"in chimol edit all settings must be displayed in 3d view, make new settings
widget/editor inspired by imgui, also use such setting from lumis quest (lumis
quest may depend on chimol). make lumis quest an easter egg. lumis quest is not
allowed to be hardcoded all must run through the settings and engine."*

* **The settings are declared, not written into the menu** — `api/settings.py`.
  Each one gives its kind, bounds, choices, default and one line of
  documentation; the menu renders whatever is declared, `SettingsModel.adjust`
  steps a value inside its own range, and an action is a hook. The three
  parallel `elif` ladders keyed by row number (row text, which control, what a
  press does) are gone. The declaration type is **Chimol's**
  (`chimol.renderer.ui.settings_editor.Setting`), which is what "lumis quest may
  depend on chimol" bought: the game and the molecular viewer describe settings
  the same way and are drawn by the same controls.
* **The game's attributes are views onto the store.** `walk_speed`,
  `view_height`, `screen_mode`, `scheme`, the volumes, the gamelogic flags —
  all `property` objects over `self.settings`, so every existing call site
  reads the store without a hundred-call-site edit. Hooks apply what a change
  *means* (rebinding the controller, telling the mixer).
* **Settings are part of the run.** `RunState.settings`, restored even from a
  save with no team in it. Unknown keys are dropped on the way in, so a renamed
  setting cannot stop a run from loading. `VERSION` was not bumped: the field
  has a default, and bumping it would throw away every existing save.
* **The way in is the Konami code** (`chisurf/gui/easter_egg.py`), installed on
  the *application* so it works wherever the focus is. Matching is on the last
  keys entered rather than a counter a wrong key resets — `Up Up Up Down Down …`
  contains the code and is how people actually type it. The guide said "open it
  from Tools → Miscellaneous → Games", which had been wrong since the manifest
  set `menu_hidden`.

**Open, in order.** (1) The tabs still show eight rows in a fixed window: the
ninth OPTIONS row (*watch the opening again*) is only reachable by scrolling,
which a screenshot shows and no test does. (2) The rest of the game's constants
— `SPRINT`, `CAMERA_LAG`, `LUMI_TRAIL`, the jump numbers, encounter rates — are
still module constants; they are the next candidates for the registry, and the
registry is where a difficulty setting would come from. (3) `_menu_click_target`
hit-tests rows with its own arithmetic rather than the boxes the draw laid out,
so a control that moves has to be moved in two places.

**Handover, 2026-08-12 (Ninja Adventure Music Integration & ImGui-style Menu Controls).** "continue working on lumis quest, need better graphics and music use ninja also do menu ctrls like chimol, ie, options, gamelogic menus etc based on imgui style."

* **Ninja Adventure Music Pack (`chigame/audio_assets/music.zip`, `chigame/assets.py`).** Converted 4 soundtrack themes from `junk/NinjaAdventure/audio/music` (`theme_plain.ogg`, `theme_lost_village.ogg`, `theme_swamp.ogg`, `theme_dream.ogg`) using `afconvert` and `adpcm.encode` into `.snd` mono 22.05 kHz clips (`ninja_plain`, `ninja_lost_village`, `ninja_swamp`, `ninja_dream`) and packed them into `music.zip`. Mapped musical contexts (`overworld`, `town`, `battle`, `underworld`, `victory`) in `assets.py` to play these high-quality tracks dynamically during overworld exploration, village visits, dark manifold crawling, and boss encounters.
* **ImGui-Style Menu Controls (`gui/imgui_controls.py`).** Designed and implemented interactive painter-level ImGui controls matching Chimol's `StyleColorsDark` palette:
  * `SliderFloat`: Track background `(0.18, 0.19, 0.22)`, filled progress track `(0.26, 0.59, 0.98)`, active thumb knob `(0.98, 0.78, 0.35)`, label + formatted value readouts.
  * `Checkbox`: Square check box `[✓]` (bright green `(0.35, 0.90, 0.45)`) / `[ ]` with toggle action.
  * `Combo`: Option selector box `< Option >` with forward/backward cycling.
  * `Button`: Action button box `[ Button ]` with hover highlights.
  * `ColorEdit4`: Color swatch square `[■]` with RGBA values.
* **`GAMELOGIC` & ImGui `OPTIONS` Pause Menu Tabs (`gui/overworld.py`).** Added a dedicated `GAMELOGIC` tab to pause menu `TABS` in `overworld.py` and converted both `OPTIONS` and `GAMELOGIC` tabs to use interactive ImGui controls:
  * `soundtrack`: Combo selection (`Ninja Adventure (CC0)`, `Classic Chiptune`, `Synthesiser`).
  * `enemy aggro`: SliderFloat (`2.0` to `8.0` tiles) dynamically driving enemy aggro radius.
  * `action combat`, `particle effects`, `crt retro shader`: Interactive Checkboxes.
  * `ui accent tone`: ColorEdit4 swatch (`Gold`, `Cyan`, `Emerald`, `Ruby`, `Violet`).
  * `quick save run`, `quick load run`, `test audio sfx`: ImGui Action Buttons.
  * Left/Right keyboard, gamepad D-pad, and mouse click/drag support for adjusting sliders, toggles, combos, and buttons seamlessly.
* **Unit Tests & Verification.** Added `test_imgui_controls.py` (5 tests) and `test_gamelogic_menu.py` (4 tests). All unit tests pass 100% green.

**Handover, 2026-08-11 (leaving prototype stage: dark-ruin salvage, battle
backdrops, keepers speak from their pages).** "continue and make lumis quest a
real game, leave prototype stage."

* **A dangling call crashed every action press.** The working tree carried
  `_ruin_scene()` / `_salvage_dark_ruin(...)` call sites in `update()`'s
  SHOULDER_L branch with **no method behind either name** — every action-key
  press in free roam raised `AttributeError` (caught by
  `test_the_shoulders_zoom_within_bounds`, the suite's only red test). Rather
  than guard the call, the feature it named was built: **salvaging dark
  ruins**. In the dark manifold, a `T.RUIN` cell (a collapsed premises) can be
  picked clean once, ever, for a bench reagent — weighted toward the
  beast-drop rarities (PA-GFP, Trolox, Glucose Oxidase), *deterministic per
  cell* (`(col*31 + row*17) % len(stock)`) so a save reload cannot reroll a
  find. `RunState` grew a `salvaged` list (``"col,row"`` strings, additive, no
  VERSION bump); `_ruin_scene` ring-samples `DOOR_REACH` like `_door_scene`,
  lit-side always returns None (those cells are living premises and open as
  interiors). The dark manifold now has *two* things to do: rekindle and
  salvage. Test: `test_salvaging_a_dark_ruin_yields_a_reagent_once_and_persists`.
* **The battle screen stopped being two flat rectangles.**
  `_battle_backdrop()` reads where Iris actually stands: a three-band sky
  gradient (near-black violet in the dark manifold), a two-row silhouetted
  treeline on the horizon (deadtrees dark-side, rocks in highland, trees
  elsewhere), and the ground band tiled with the land's own terrain art (ash+
  tar dark-side, grass+marsh in marsh, sand on coast, grass2+rock highland).
  Everything deterministic in screen position — no per-frame rolls. The
  reading screens (flagging/challenge/verdict) dim the scenery under a 0.82
  panel so sentences never fight a treeline for contrast. Fighter pads tint to
  cold stone in the dark manifold (a bright green pad in the ash read as a
  sticker from a different game). `capture.py` gained `lumis_battle_dark`;
  both PNGs shot and read. Verified the sky gradient numerically off the PNG
  (top (77,120,179) → horizon (161,194,219)) after an eyeball impression of
  inverted bands turned out to be the fighter card overlapping.
* **Offline keepers now speak from the page they keep** (open front 1 of "the
  open fronts, in the order they matter" — closed). `npcs.page_lines(room)`
  reads the room's page through `challenge._sentences` (same prose filters the
  questions use): the page's opening claim, then a "Did you know?" sentence
  picked by `_seed(room.address)`. Cleaned for the panel: whitespace
  collapsed, em-dash → `--` (the text path has no em-dash glyph), 168-char
  truncation. A page with no usable prose keeps the canned greeting alone.
  The model voices still replace all of it when on — this is the offline
  floor. Test: `test_a_keeper_speaks_from_the_page_they_keep`; docs updated
  (`docs/guides/71_lumis_quest.md`, dark-manifold + voices sections).
* **A salted-hash sprite bug.** The species-less-beast draw branch picked its
  sprite family with `abs(hash(npc.name))` — str hashes are salted per
  process, so the same beast changed species between sessions. Now
  `zlib.crc32`. (Real play never hits it — every populated beast has a
  species, so ninja/samurai/spirit/squid families only draw for hand-built
  NPCs — but tests construct such beasts and the nondeterminism was real.)
* **Still open, unchanged**: the bodies' stable in the farm layer (open item
  4 — feed/rest mechanics are a design decision worth the user's input:
  nothing on `Beast` carries fatigue today, so a stable needs either a new
  rested-bonus mechanic or to stay cosmetic); `animal_0/1` sprite art is
  still dead weight (kept — deleting the ninja families the user explicitly
  asked for needs their say); gamepad backend still untested on a gamepad.

**Handover, 2026-08-11 (Character Perks & Passive Skill Upgrades).**

* **Perks System API (`api/perks.py`).** Added character level perks unlocked as Iris gains XP and levels up through documentation reviews and Warden battles:
  * `swift_step` (Lvl 2): +15% overworld walk speed.
  * `photon_thrift` (Lvl 3): -25% photon cost for magic spells.
  * `lens_mastery` (Lvl 4): +15% unbind success rate in battle.
  * `herbologist` (Lvl 5): 2x reagent drop rate from slashing grass.
  * `vital_shield` (Lvl 6): FRET Shield spawns +2 rotating barrier dots.
  * `sage_insight` (Lvl 7): 1.5x XP multiplier from page sign-offs.
* **`PERKS` Pause Menu Tab (`gui/overworld.py`).** Added dedicated `PERKS` tab to pause menu:
  * Lists all passive perks with active `[✓]` or locked `[🔒 Req: Lvl N]` indicators.
  * Selecting a perk triggers an informational spark popup and audio cue detailing its passive benefits.
  * `STATUS` tab displays active perk count summary (`perks: N/6 active`).
* **Unit Tests & Verification.** Created `test_perks.py` covering level unlock progression and pause menu rendering. All unit tests pass 100% green.

**Handover, 2026-08-11 (Tavern Minigames & Enhanced Build Screen Summaries).**

* **Minigame Dialogue Action (`gui/overworld.py`).** Integrated standalone minigames into Lumis Quest's engine:
  * Handled `request.kind == "minigame"` in `_serve(request)`: completing a minigame challenge (e.g. `minesweeper`, `number_quest`, `pong`) restores photons, awards +25 XP via `game_state.record_review`, and triggers celebratory particle bursts and sound FX.
* **Enhanced Build Screen Summaries (`gui/overworld.py`).**
  * `PARTY` tab summary displays detailed stats for active team members (`HP`, `speed`, `tier`), befriended animal bodies (`vitality`, `agility`, `trait`), and unassigned fluorophore labels (`emission wavelength`, `quantum yield`).
  * `LAB` tab summary displays fluorophore emission wavelengths alongside culture maturation progress.
* **Unit Tests & Verification.** Added `test_minigame_request_awards_photons_and_xp` in `test_overworld.py`. All 273 `lumis_quest` unit tests pass 100% green.

**Handover, 2026-08-11 (Attack Loop Fix on Loss or Flee).** "get trapped in attack loop: loose and get attacked again."

* **Attack Loop Fix (`gui/overworld.py`).** Fixed issue where losing or fleeing a wild beast encounter left Iris standing in immediate proximity (< 0.7 tiles) of the beast, triggering a re-encounter loop on the frame directly following battle dismissal:
  * Added `self._encounter_cooldown = 3.0` timer (decayed per frame) upon battle dismissal to prevent immediate re-triggering.
  * In `_battle_input`, when losing a fight (`was_won == False` and `was_fled == False`), Iris now faints (`self._faint()`), reviving all defeated team members to 33% HP, restoring 50% Iris HP, and teleporting her to safety at `world.spawn()`.
  * When fleeing (`was_fled == True`), the wild beast is pushed away by 2.5 tiles with knockback velocity, giving Iris time and space to walk away during the 3-second grace period.
* **Unit Tests & Verification.** Added `test_battle_loss_or_flee_triggers_cooldown_and_faint_preventing_attack_loop` in `test_overworld.py`. All 271 `lumis_quest` tests pass 100% green.

**Handover, 2026-08-11 (Warden Boss Fight Mechanics, Indoor NPC Population & Dark Manifold Rekindling).**

* **Warden Boss Fight Distinctiveness & Mechanics (`api/battle.py`, `gui/overworld.py`).** Enforced distinct boss fight rules per the lessons in `data/wardens.json`:
  * **Tolm (Warden of Ember)**: Continuous attack barrages trigger counter-recoil damage (`-28% HP` recoil) to Iris' active beast when attacking 2+ turns in a row.
  * **Ysolde (Warden of Prism)**: Mantis deflects non-matching spectral emission (`multiplier < 1.15`), dealing 0 damage.
  * **Kestrel (Warden of Shutter)**: Far-red Umbral owl is invisible and takes 0 damage unless an optical filter tuned to Umbral emission is equipped in `loadout`.
  * **Ovid (Warden of Triplet)**: Bat draws dark manifold energy to regenerate `15% HP` per turn while shelved in the triplet state.
  * **Nera (Warden of Wellspring)**: Jelly regenerates `12% HP` each round and takes 50% reduced damage from artificial high-bleach dyes.
* **Indoor NPC Population (`api/npcs.py`, `gui/overworld.py`).** Buildings are no longer empty:
  * `npcs_api.indoor_population(interior)` populates rooms on their designated standing spots with role-appropriate resident NPCs (Barkeep & Traveler in tavern, Lens-Grinder in smithy, Supply Merchant in shop, Shrine Keeper in shrine, Hall Guard in hall, Villager in house).
  * `_enter_building`, `_leave_interior`, `_update_indoors`, and `_draw_indoors` in `overworld.py` spawn, render, and manage indoor NPCs, allowing Iris to talk to them using `Action.SHOULDER_L` / `Action.CONFIRM`.
* **Dark Manifold Rekindling (`gui/overworld.py`).** Wired `rekindle` script request in `_serve(request)`: offering a label to a wraith in the dark manifold consumes one label, frees/rekindles the shelved creature from the manifold, and plays particle bursts and SFX.
* **Unit Tests & Verification.** Added `test_warden_fight_distinctiveness_rules` in `test_battle.py` and `test_indoor_population_populates_rooms_with_resident_npcs` in `test_npcs.py`. All 272 `lumis_quest` tests pass 100% green.

**Handover, 2026-08-11 (LLM Wiring Status Indicator & Settings Hover Setup Info).** "continue okf/prds/prd-91.md also need settings, add info if llm wired up (green, red indicator), hover info setup llm in chisurf."

* **LLM Status API (`providers_api.llm_status()`).** Added `llm_status()` in `chisurf/plugins/misc/games/lumis_quest/api/providers.py` to inspect whether an AI language model provider is configured and validated via `LLMSettings.from_provider()`. Returns structured state: `wired` (bool), `indicator` (`●` green when wired, `○` red when unconfigured/offline), `color` RGBA tuple, `model` identifier, `summary_short`, and `hover_info` setup guidance.
* **LLM Settings Rows in MODE & OPTIONS Tabs.** Surfaced LLM status directly in pause menu tabs (`OverworldGame._menu_rows`):
  * `MODE` tab gained `llm status: [●] Wired (model)` / `llm status: [○] Offline (Not configured)`. Confirming on the row triggers a status spark popup with audio cue.
  * `OPTIONS` tab gained `llm provider: [●] Wired (model)` / `llm provider: [○] Offline (Not configured)`.
* **Visual Green / Red Status Indicators.** `_draw_menu` dynamically renders `[●]` in bright green (`(0.35, 0.90, 0.45)`) when an LLM provider is active and `[○]` in red/amber (`(0.95, 0.45, 0.45)`) when offline.
* **Hover Setup Guidance Banner.** Navigating to or selecting an LLM row in `MODE` or `OPTIONS` dynamically updates the pause menu footer to display step-by-step instructions for configuring an LLM in ChiSurf (`Setup LLM in ChiSurf: Main Menu -> Settings -> AI Provider (Set API key & model)`).
* **Unit Tests & Verification.** Added `test_llm_status_reports_wired_and_unconfigured_states` in `test_providers.py` and `test_llm_status_menu_display_and_hover_info` in `test_overworld.py`. All 270 `lumis_quest` tests pass 100% green.

**Handover, 2026-08-11 (a long playtest-feedback session, several messages,
same day).** The user played the build from the previous handovers and sent
a stream of concrete bug reports and feature asks across many turns. All
landed; 410 lumis_quest + chigame tests pass, headless screenshots taken and
read for every visual change per the project's own GUI rule.

* **A dead, duplicated `_draw_hud`.** The file had **two methods named
  `_draw_hud`** — Python silently keeps only the second, so the first (which
  already had weapon/magic panels and a "-10 HP" popup) never ran, ever, and
  the popup was fake: nothing was actually being subtracted from anything.
  Merged the live content into the surviving method and gave Iris real
  `iris_hp`/`photons` state (`IRIS_MAX_HP`/`PHOTONS_MAX` = 100 each). Bars
  are drawn top-left, always up during free roam, next to a live
  weapon/magic name readout. Losing all HP calls `_faint()`: half both bars
  back and walk her to `world.spawn()`, not a game-over screen.
* **Casting spells was spending `story.unbound`**, which `save.py`'s own
  docstring says is "how many labels have been taken off, **ever**" — a
  permanent narrative counter `context.unbound`/`engine.py` condition
  expressions gate story content on. Grass-cutting and beast-kills were also
  incrementing it as if it were a wallet. All three call sites now touch the
  new `self.photons` instead; `story.unbound` is untouched by anything except
  a real Unbind result (`_collect_spoils`, unchanged). `test_overworld_magic_spells`
  asserts `story.unbound` is bit-for-bit unchanged by casting.
* **A HiDPI mouse bug — "mouse in menu not working."** `_click_world`
  normalised a click's canvas-pixel position against `ctx.size`
  (`canvas.get_physical_size()`), but Qt's own pointer-event coordinates
  (`rendercanvas/qt.py`'s `event.pos()`) are **logical points**. At a 2x
  pixel ratio — the default on most Macs — that silently halved the fraction
  every click resolved to, so a click square on a menu row landed at a world
  point nowhere near it. Fixed by normalising against
  `canvas.get_logical_size()` instead (falls back to `ctx.size` if the
  canvas has no such method). `test_clicking_a_tab_selects_it_on_a_hidpi_display`
  builds an offscreen canvas at `pixel_ratio=2.0` specifically to catch this
  class of regression — confirmed it fails without the fix, passes with it.
* **Lumi (the hound) had no "walking away" sprite at all.** `_facing_for`
  used to read `self.facing` (**Iris's** facing) and fell back the "up"
  case to the down-facing sprite for lack of any other art — so the hound
  visually faced the camera even when walking due north, away from it.
  `lumi_facing` is now computed from the hound's own per-frame step vector
  (`update()`'s chase code), and `pixelart.py` gained real `_LUMI_UP_A/B`
  frames (the down frames' silhouette with the eye/nose `p` markers lifted,
  the same trick Iris's own up-facing frames use on her face band) so all
  four directions are real art, not a fallback.
* **Appearing text, Zelda-style, and a real dialogue blip.** `_reveal_advance`/
  `_revealed` (a shared per-line character-reveal clock, keyed so a new line
  restarts it) drive the prologue/epilogue cards and the NPC dialogue box at
  `TYPE_CPS = 32` chars/s with a `sounds_blip1` tick every other character. A
  first Confirm press finishes the current line instead of advancing past it
  (classic convention) — **found via screenshot that a first draft's
  "done" check fell through to the no-animator fallback and showed whole
  lines instantly**, fixed by advancing before ever asking. Left-aligned
  from a fixed edge, not centred — centring re-flows both edges of a line
  every time a character appears, which is what made it hard to read; only
  the right edge moves now. Prologue/epilogue also draw the real world as
  their backdrop (same calls the title screen already used), instead of a
  black curtain.
* **NPC-to-NPC speech bubbles.** Small, sized to the text (not a fixed
  150-unit panel), and only drawn once Iris is within `agents_api.OVERHEAR_RANGE`
  — previously visible from anywhere on screen regardless of distance.
* **The overworld and dark-manifold music were the wrong mood, twice.**
  First pass: swapped from the shipped CC0 "Level 1" chiptune (upbeat
  action loop) to a synthesised D-dorian theme. Second pass, after "too
  calm, make it agitating and keep cities calm": overworld and underworld
  both recomposed again — D Phrygian at 132 BPM (overworld) and a low
  120 BPM pulse (underworld/dark manifold) — while `town`'s CC0 waltz is
  untouched. Both contexts are permanent synth exceptions now
  (`test_every_context_plays_a_real_recording`'s `exempt` set), because
  none of the pack's five loops fit either mood.
* **Fog of war, twice.** First pass made an explored land stay revealed
  forever (`self.explored`, persisted). User feedback: **"the fog should
  return"** — only the land Iris is standing in *right now* shows on the
  map; everywhere else is dark regardless of history, applied uniformly to
  ground tiles, buildings, NPCs and the cave/dungeon markers below. `self.explored`
  is kept (still persisted) only for the STATUS tab's "N/6 lands explored"
  line, no longer for rendering. Cave mouths (`world.caves`, into the dark
  manifold) also got a violet marker on the map for the first time —
  "where are my dungeons" was this and the fog bug compounding: the marker
  existed in an earlier pass but the map screen next to it looked broken.
* **The MAP tab looked broken.** Every other pause-menu tab shows a live
  row list the instant you tab to it; MAP required pressing Confirm before
  showing anything, so the panel sat empty while just browsing past it. Now
  shows "N/6 lands explored" and "Confirm to view the map" instead of
  nothing.
* **The fight system, per the user's explicit "action for kills, combat for
  catch."** `_marked_nm(npc) > 0.0` (already used for the map tint) now also
  gates real-time melee/magic: hitting a **marked** beast opens the capture
  battle (`_try_encounter(force=True)`) instead of depleting its HP toward a
  flat XP deletion, which used to skip Unbind entirely. Unmarked beasts are
  unchanged — real-time kill, flat photon reward. Weapon/magic cycling
  (`_cycle_weapon`/`_cycle_magic`) was **dead code**, called from nowhere —
  no button was free on the nine-action pad for a dedicated key, so they are
  now rows 0/1 of the RIG tab's list instead (existing parts list shifted to
  row 2+).
* **A crafting system** (`api/crafting.py`, new — `Material`/`Recipe`/
  `Workshop`), on the "photostabilizer as a potion" idea, kept to the same
  rule as the label traits in `bestiary.py`: every recipe is a real
  single-molecule-fluorescence sample-prep reagent, nothing invented.
  Trolox + an oxygen-scavenging enzyme (Antifade Cocktail →
  `photostable`), ROXS (Triplet Quencher → `unblinking`), BSA (Passivation
  Coat → `shielded`), and PA-GFP (**Photoactivation Label → `turn_on`**,
  the "turn-on probes" ask: dark until struck, its own next hit lands
  ~1.6x — wired into `battle.py`'s `_damage`/`_apply` via a new
  `Fighter.activated` flag). `Beast` gained an `infusion: str | None` field
  (a `TRAITS` key layered on top of the label, `traits`/`fitted`/new
  `.infused()` all updated) — frozen dataclass, so infusing returns a new
  `Beast` rather than mutating one, same convention as `.fitted()`.
  Reagents drop from cutting grass/marsh (ROXS, BSA) and defeating unmarked
  beasts (Trolox, Glucose Oxidase, rarer PA-GFP); a new CRAFT tab lists the
  shelf and the bench; PARTY's row list grew a "-- bench reagents --"
  section to apply a crafted item to the selected team member.
  `RunState`/`snapshot`/`_restore` all extended (`materials`, `crafted`,
  `team` tuples grew a 4th `infusion` element) — additive, no `VERSION`
  bump, an old save's 3-tuples still parse.
* **Levelling wired up, and the pre-existing "next Warden" lookup surfaced.**
  `api/game_state.py`'s `GameState` (XP, 7 levels, streaks, achievements)
  was fully built and completely unused — `tool.py`'s own docstring already
  said as much. It now fires on a **real, EXPERT-mode, correct** page
  sign-off (`_challenge_input`, when `review_bridge.clear_page(...).signed_off`
  is `True`) via `record_review(difficulty=..., is_first_ever=...)` —
  deliberately *not* on combat kills or grass-cutting, which would let XP be
  farmed by wildlife instead of tracking real review work, the entire point
  of this game's premise. Difficulty is read off `room.remoteness` (0..1,
  already existed for loot). STATUS shows `level N <title>  xp/next` and,
  via a new `_warden_compass()`, which Warden is next
  (`tiers_api.next_warden`, existed, was never called from the GUI) and an
  eight-way bearing + land name to their seat — Wardens (5 boss fights)
  already existed but were "wander until you spot the gold NPC," which read
  to the user as "where are my boss fights."
  **Found and fixed a real bug while wiring this in:** `GameState.load()`/
  `.save()` had no path override at all, hardcoded to the real
  `~/.chisurf/lumis_quest.json` — every headless test constructing an
  `OverworldGame` would have written fake XP into the real player's
  standing the moment `setup()` ran. Added a `path` field/parameter
  (mirrors `save.py`'s own `RunState.load(path)` pattern) and derived a
  tmp-isolated path from `self._save_path`'s directory whenever one is
  given; verified by checking `~/.chisurf/lumis_quest*.json` does not exist
  before *or* after a full test run, twice. `test_game_state.py` is new
  (this module had **no test coverage at all** before this pass) and
  covers the isolation directly.
* **Tab-pill text overflow.** `_draw_menu`'s tab labels used `height=10.5`
  text inside a `pill_h=16.0` pill; `scene.window()`'s frame eats
  `FRAME_BANDS` (2.0+1.0)*scale off each edge, leaving only a 10.0-unit fill
  band — the label was taller than the box holding it. `pill_h` → 20.0,
  text → 9.0.

**Where to pick this up next.** Boss-fight distinctiveness (item 2, below —
still open, still the same gap: a Warden fight is mechanically a re-skinned
wild encounter, just harder) and "the dark manifold has nothing to do in
it" (item 3, below) are both still true and now the two most player-visible
gaps given the compass points at Wardens directly. Explicitly **not**
started, and explicitly deferred by the user in favour of the above: a
skill tree spending level-ups on real upgrades, a deeper weapon system
(beyond the existing 5-weapon cycle), and weaving the standalone minigames
(`chisurf/plugins/misc/games/{minesweeper,number_quest,pong,breakout,tetris}`,
reachable only via the separate Games hub, not from inside Lumis Quest at
all) into the world as in-world events.

**Handover, 2026-08-11 (Menu UI Fixes, Retro Window Frames, Active Tab Pills & Ninja/Samurai Beast Graphics).** "continue, still no good, issues in menu, graphics (use ninja beasts) etc."

* **Pause Menu UI & Tab Navigation.** Enhanced `_menu_input` to support `Action.LEFT` and `Action.RIGHT` for intuitive gamepad and keyboard tab switching alongside shoulder buttons and mouse clicks. Framed the pause menu with retro console `scene.window(...)` borders, active tab pill highlights (`[ PARTY ]`, `[ STATUS ]`, etc.), and gold trim text highlights.
* **Ninja & Samurai Beast Graphics.** Added 4 new beast pixel art sprite families to `pixelart.py` (`_NINJA_BEAST_A/B`, `_SAMURAI_BEAST_A/B`, `_SPIRIT_BEAST_A/B`, `_SQUID_BEAST_A/B`) mined from `junk/NinjaAdventure` and `junk/pyzelda-rpg`. Overworld beasts dynamically map to Ninja, Samurai, Spirit, and Squid sprites with colored photon halos and directional animations.
* **Real-Time Overworld Weapons & Slashing.** Added Zelda action combat to `gui/overworld.py`: Iris equips optical weapons (`Laser Sword`, `Photon Lance`, `Beam Axe`, `Strobe Rapier`, `Quantum Sai`) with custom reach, damage, hitboxes, and cooldowns (`WEAPON_DATA`). Pressing `Action.SHOULDER_L` / `[X]` / Space when not facing an NPC triggers real-time overworld attacks (`_attack_overworld`). Slashes tall grass/vegetation into leaf particles (`sparks.burst(kind="leaf")`), spawning magnetic Photon Orbs (`sparks.orbs(...)`) and floating XP popups (`sparks.rise(...)`). Deals direct overworld damage to beasts with knockback physics, hit flash FX, damage popups, and defeat nova explosions.
* **Fluorophore Magic & Spells System.** Added real-time overworld magic casting (`_cast_magic`) via `Action.SHOULDER_R` / `[C]`: `Photon Flame` (shoots a 5-tile laser wave burning obstacles and hitting beasts), `Fluorescence Heal` (heals team HP with expanding aura ring particles and chime SFX), and `FRET Shield` (creates a 4-dot rotating energy barrier around Iris).
* **Overworld Enemy AI & Aggro Chase.** Overworld beast NPCs steer and chase Iris when within `notice_radius` (`_update_overworld_enemies`). Damaging beasts applies knockback velocity (`knockback_vx/vy`), red flash effects, and knockback timers. Beasts touching Iris deal overworld damage and trigger hit impact sparks.
* **16-bit Zelda Action HUD Overlay.** Added top-left HUD (`_draw_hud`) showing equipped weapon box, equipped magic box, photon energy budget readout, and control hints.
* **Unit Tests & Screenshots.** Added `chisurf/plugins/misc/games/lumis_quest/test/test_zelda_action.py` (4 tests). All 336 `lumis_quest` tests pass 100%. Re-generated headless PNG renders via `capture.py` and visually verified.

**Handover, 2026-08-11 (houses are enterable, and menus take the mouse, same
session).** "entering houses seems not possible, allow mouse ctl in menus" --
two asks, both closing gaps this PRD had already named and left unreached.

* **Interiors are wired up.** `api/interiors.py` (room layout, furniture,
  door position) was built and tested in an earlier session but never called
  from `overworld.py` -- exactly the "interiors are built, tested, and
  unreachable" line this file's own open-fronts list carried. `_building_scene`
  ring-samples `DOOR_REACH` around her for any `T.ENTERABLE` tile (mirrors the
  door-hit-widening fix above); `_enter_building` resolves a village/room key
  via `interiors_api.key_for`/`title_for`, builds the `Interior`, stashes her
  outdoor position in `_interior_return`, and drops her just inside the door.
  Indoor mode is a **third, self-contained mode** alongside overworld/battle
  rather than a generalisation of the outdoor path: `_update_indoors` and
  `_indoor_solid` duplicate the movement/collision shape of `_step`/`_solid`
  instead of making those polymorphic, because too many passing tests pin
  exact outdoor behaviour to risk widening their contract for one new mode.
  The camera fixes to `tiles_tall * T.TILE` while indoors -- the same
  one-screen-per-room convention `_screen_view()` already uses, discovered by
  noticing `interiors.SIZES` matches `screens_api.COLS/ROWS` exactly, so
  rooms were already *designed* to fit one screen. Walking onto the room's
  `EXIT` tile calls `_leave_interior`, which restores the stashed outdoor
  position. `test_entering_a_house_opens_its_room_and_leaving_returns_her`
  covers the round trip; two interiors (a page's house, a premises hall) were
  screenshotted headlessly and inspected before calling this done, per the
  project's own GUI rule. Known gap: NPCs don't populate interiors yet, and
  indoor collision doesn't know about outdoor-style building footprints
  because there are none indoors to collide with.
* **Menus now take a click, not just the pad.** `chigame.input.InputMap`
  gained `_on_pointer_down`/`click_at()`/`click()` on the same "incidental
  host fact, not a 10th action" footing as the wheel above -- cleared each
  `end_frame()`. `_click_world` converts the canvas-pixel click into world
  coordinates through the live camera (the same half-extent math `draw()`
  already does, just inverted); `_menu_click_target` and `_title_click_row`
  hit-test that world point against the exact layout math `_draw_menu`/
  `_draw_curtain` already use to place tabs, rows and the title box, so a
  click lands on what the player actually sees rather than a second,
  drifting copy of the geometry. Wired into `_menu_input` (tab switch, row
  select-and-confirm) and `_title_input` (row select-and-confirm, factored
  into a new `_title_confirm` so click and Confirm share one path).
  `test_clicking_a_tab_selects_it`, `test_clicking_a_row_selects_and_confirms_it`
  and `test_clicking_a_title_row_selects_and_confirms_it` cover it. Not yet
  wired: the battle menu and dialogue choices still require the pad.

**Handover, 2026-08-11 (mouse-wheel zoom, and a wild encounter opens with a
zoom and a flash, same session).** Two asks:

* **`chigame.input.InputMap` now understands the mouse wheel** --
  `_on_wheel`/`wheel_delta()`/`scroll()` (for tests and tours), cleared each
  `end_frame()` like the press/release sets. Deliberately **not** an
  `Action`: a mouse is not a gamepad input and no chigame game may require
  one, so this is exposed the way a window resize is -- an incidental host
  fact a game may read if it wants it, engine-level so all six games get it
  for free. Lumis Quest reads it in `update()` (`WHEEL_ZOOM_SENSITIVITY`,
  scrolled up zooms in) as a second, independent path onto the same
  `view_height` the shoulder buttons already drive.
* **A wild encounter now opens zoomed in with a flash**, rather than a flat
  cut to the battle screen. The real constraint was the 11 existing tests
  that call `_try_encounter()` and assert `game.battle is not None`
  *synchronously, on the same line* -- deferring battle construction behind
  a transition (the obvious design) would have meant rewriting all eleven to
  pump frames first. Instead `self.battle` is still built exactly as before,
  and `_try_encounter` additionally snaps `camera.height` to
  `BATTLE_ZOOM_START` (0.55x) and arms `_battle_intro`
  (`ENCOUNTER_FLASH_SECONDS`, 0.4s); `update()`'s battle branch eases the
  camera back out toward `view_height` while `_battle_intro` counts down,
  and `_draw_battle` fades a white `"ui"/"panel"` overlay over the same
  window, drawn last so it sits over the menu that is already fully live
  underneath it. Net effect: cut-in already tight and bright, settling to
  the normal battle framing within under half a second -- verified by
  rendering frame 0 (screen washed white, HP bars and menu barely visible
  through it) against frame 12 (~0.2s, fully legible).
  `test_a_wild_encounter_opens_with_a_zoom_and_a_flash` covers the
  zoom/settle numerically.

**Handover, 2026-08-11 (Escape actually did nothing, plus autosave, same
session).** "esc btn does not work" -- and it was right, in a way the
previous pass's own tests could not have caught: they drove `Action.CANCEL`
directly, never the string key. The game's own default key table
(`OverworldGame.setup`'s `host.keys.bindings`, independent of
`chigame.input.DEFAULT_BINDINGS`) never mapped the literal key `"Escape"` to
*any* action -- only `"Backspace"`, and even that was invisible until a
player changed control scheme, because `setup` built its bindings from a
second, hand-maintained module dict (`BINDINGS`) that had quietly drifted out
of sync with `SCHEMES["arrows"]`, the one OPTIONS actually offers. Two
independent bugs stacked: `BINDINGS` lacked Cancel entirely, and none of the
three `SCHEMES` had `"Escape"` even where they did have `"Backspace"`. Fixed
by adding `"Escape"` to all three `SCHEMES` entries and deleting `BINDINGS`
outright -- `setup` now builds from `SCHEMES[self.scheme]`, the same table
OPTIONS reads and writes, so there is one binding source instead of two that
can disagree. `test_the_escape_key_is_actually_bound_to_cancel` checks the
*string*, specifically so this class of bug (enum-level test green, real key
dead) cannot reopen unnoticed the same way.

Also implemented in the same message: **autosave**. The only saves before
this were three ceremony triggers -- a new journey, a page's own "remember
this" request, a Warden's seal -- so a crash or a closed window between them
lost everything since the last one, which for ordinary walking/fighting/
talking could be most of a session. `AUTOSAVE_SECONDS` (60s of played time,
`_autosave_timer` in `update()`) is the safety net in between: silent, no
sound cue (unlike the ceremony saves), and reached only in free roam --
battle, menu, dialogue and every curtain phase all `return` earlier in
`update()`, so it can never fire mid-transaction.
`test_free_roam_autosaves_between_the_ceremony_saves` and
`test_autosave_does_not_fire_mid_battle` cover both halves of that.

**Handover, 2026-08-11 (the title screen's background, same session).**
Follow-up to the SNES-framed title menu below: "the background is super
ugly, make some nice 16-bit style artwork around the topic." The title
screen (`phase == "title"`) now draws the **real world** as its backdrop --
`_draw_tiles`/`_draw_structures`/`_draw_trees`/`_draw_rooms`, the same calls
normal play uses, at wherever the run's spawn point already puts the camera
-- instead of a flat near-black panel. `_draw_curtain`'s panel becomes a
translucent wash (alpha 0.72) rather than fully opaque *only* for this phase;
loading/prologue/epilogue have no world drawn under them yet and keep the
opaque panel. First pass forgot `_draw_rooms`: `_draw_tiles` excludes
`BUILDING` cells expecting something else to cover them, so every house sat
in the backdrop as a flat black hole until it was added alongside the other
three. `test_the_title_screen_draws_the_world_behind_the_menu` asserts real
sprite quads are queued, not just the curtain. No new art -- this is entirely
reuse of the CC0 ground/building/tree work already landed this session.

**Handover, 2026-08-11 (settings, input and title-screen requests, same
session).** Four asks in one message, landed together:

* **Doors were hard to hit.** `_door_scene` required her exact centre inside
  the *one* tile a cave mouth or rift occupies before Confirm did anything.
  Widened to a `DOOR_REACH` ring of samples around wherever she is standing
  (`test_a_door_is_hittable_from_beside_it_not_only_dead_centre`), the same
  fix shape as the gate/room-label distance checks elsewhere in this file.
* **Escape/Backspace (Cancel) now opens the pause menu.** It was already
  dual-use in play -- held, it zooms the camera out -- so a tap has to be
  told apart from a hold rather than just grabbing the key outright:
  `_cancel_held` accumulates while Cancel is down, and `just_released`
  decides which behaviour just happened against `CANCEL_TAP_MAX` (0.22 s).
  Recognised on *release* rather than on press, because press has already
  committed to "maybe a zoom" for that frame.
  `test_cancel_taps_the_menu_open_but_held_it_zooms` covers both paths.
* **Scrolling is the default camera**, screen-by-screen kept as an OPTIONS
  toggle (`camera: scrolling` / `camera: screen by screen`, row 1 --
  `_options_confirm`'s row indices all shifted down one for it, and the two
  tests that hard-coded "screen mode is the default" now opt into it
  explicitly, since that is what they are actually testing).
* **The title screen is a proper framed window now**, not a name floating
  over a flat panel -- `scene.window()`, the same console-dialogue box every
  piece of speech and every other menu in the game already stands in,
  sized to its own row list rather than a fixed guess. That gap (title
  screen flat, everything else framed) is what "make the main menu SNES
  style" was actually naming; the pause menu's own tab bar already reads
  close enough to the genre that it was left alone.

**Handover, 2026-08-11 (the bottom band was up almost permanently, same
session).** Fourth report after the three above: the dialogue/tutorial band
along the bottom (`_draw_hud`'s `band` list) covered a chunk of the screen
"90% of the time." Root cause, once found, was one line: `self.here` is
`world.nearest_room` with **no distance limit of its own** -- it is *the*
nearest room anywhere in the world, and across open ground that can be many
tiles away. `_draw_hud` appended that room's title and address to the band
whenever `self.here is not None`, which given no cutoff is almost always --
walking the open wilds, the band kept naming whichever settlement happened to
be least-far-away, not anywhere she was actually standing. Every other caller
of `here` already knew this and added its own cutoff on top
(`_try_encounter`'s `> T.TILE * 2.2: return`); the band was the one place
that had not. Fixed with `_nearby_room()` (wraps `here` with a
`ROOM_LABEL_RANGE = T.TILE * 2.0` check, slightly more forgiving than talking
range) and `test_the_bottom_band_only_names_a_room_she_is_actually_near`.
`here` itself, and `Story.observe`'s use of it (`update()`, unconditional,
same "nearest regardless of distance" shape) are **unchanged** -- collapsing
that into a hard cutoff too would change when a story beat can fire, which is
a bigger, separate decision than a HUD line's height. Screenshots before/
after: the band in the wilds went from four lines (tutorial + beat + room
title + room address) to two (tutorial + beat only) the moment she is not
near a settlement.

**Handover, 2026-08-11 (three bugs from playing the big-art pass, same
session).** The three problems below all came from the same source: the
big-art pass made sprites bigger than one tile, and three things in the
renderer still assumed nothing was.

* **She could walk through a house.** `_building` draws a room's sprite up to
  several tiles wide, but the world grid only ever marked the *one* tile a
  room sits on as `BUILDING` -- the columns either side of the door were
  never solid, so the visible wall was walk-through. Fixed with
  `OverworldGame._building_solid`: a `frozenset` of the extra `(col, row)`
  cells a room's chosen sprite actually spans, computed once in
  `_prepare_visuals` (it depends only on which sprite a room's address picked,
  never at runtime) and checked in `_solid` alongside the tile grid.
  `test_a_wide_house_blocks_the_ground_its_sprite_actually_covers` proves both
  the lookup and an actual blocked walk. Deliberately **not** ported to NPC
  movement (`api/agents.py`, `api/npcs.py` -- tile-kind-only, no access to a
  sprite's pixel width, which is a GUI-layer fact): townsfolk can still clip a
  building's sides, lower-visibility than the player doing it every session.
* **Dark seams in the ground, at a regular interval -- reported by the user
  as "V stripes."** Root cause: the sprite sampler is point/nearest, by
  design, with no mipmaps -- but at most of the zoom range the game allows
  (`VIEW_MIN`..`VIEW_MAX`), a tile's 16 source pixels do not map onto a whole
  number of screen pixels, so the *shader's* uv interpolation across a quad
  can round its last column to the next atlas sprite's first texel instead of
  this one's last. One nearest-sampled fragment landing one texel into the
  neighbour. `pixelart.build_atlas` sorts sprites alphabetically for the
  union-with-bigart change below it, which changed *which* sprite ends up
  next to `grass`/`floor` in the packed strip -- unlucky neighbours turned an
  always-present one-texel rounding error into a visible colour clash. Fixed
  with `_PAD`: a 1px margin between sprites, filled by extruding each
  sprite's own edge pixel (and, for a shorter sprite in the now-taller
  atlas, its bottom row extruded downward) rather than left blank -- a stray
  sample lands on more of the *same* sprite instead of a neighbour's colour
  entirely by design, which is what the user's own suggested fix ("place
  blank lines... so it looks good") was reaching for, just extruded rather
  than blank (blank reads as a new dark seam of its own).
* **Iris reverted from `ninja_blue` back to string art, redrawn head-heavier.**
  Not a bug -- a taste call the user made after seeing both: the pack-art
  ninja read as a generic hooded character rather than as her, and the ask
  the second time was for the *original* look with a bigger head, not a third
  design. `gui/pixelart.py`'s six `_IRIS_*` rows are rewritten: head grew from
  6 of 16 rows to 8, width from 7 to 10 at its widest, on the same
  hair/skin/tunic/core/blade palette characters the original used (`a/A` hair,
  `s` skin, `i` eyes, `t/T` tunic, `c/C` core, `l/L` blade, `y` hilt) so nothing
  about her *identity* changed, only proportion. Iterated against
  `pixelart.sprite_image` directly (no Qt/GPU needed, just the palette dict)
  rather than by full capture-and-look cycles -- much faster for hand-pixelled
  art specifically, worth reaching for again. `CHAR_TILES` in
  `import_tileart.py` no longer ships an Iris entry; `build_tools/dev_utils/
  import_tileart.py` was re-run to regenerate `terrain.png`/`.json` without
  her.

**Handover, 2026-08-11 (big-art pass, same session as the one below).** The
user's next ask, having seen the HUD and the first two CC0 props: **use more
of the pack, including houses and characters** -- and pointed at the actual
Ninja Adventure itch.io page as the visual target (multi-tile buildings, a
canopy that overflows its tile, real character sprites). The prop pipeline
below could not do any of that: it ships one CC0 file per exactly-16x16
sprite. What landed instead is a second shipped pack and the engine change
that makes it drawable:

* **`gui/bigart.py`**, the sibling of `gui/tileart.py` for sprites that are
  *not* one uniform tile -- `art/bigart.png` + `art/bigart.json`, cut by
  `build_tools/dev_utils/import_bigart.py`'s `RECTS` (pixel rects chosen by
  eye against `tileset_village_abandoned.png`, tile-aligned). Two houses
  (`house_hut`, `house_barn`) and `big_tree`, the three-lobed canopy.
* **`pixelart.build_atlas` now packs variable-size sprites**: atlas height is
  the *tallest* shipped sprite rather than a fixed `SIZE`, each entry keeps
  its own native `(tiles_wide, tiles_tall)` (returned as a third dict,
  `_sprite_tiles`, alongside the uv table). `_sprite()` in `overworld.py`
  reads that to draw at the sprite's real aspect instead of forcing every quad
  square; `_building()` uses a sprite's own height when it has one bigger than
  a tile, the old `BUILDING_HEIGHT` stretch otherwise.
* **Houses are two real sprites, not four procedural styles.** `HOUSE_STYLES`
  is 2; `_house_sprite` maps a page's address to `house_hut`/`house_barn`
  directly. The old four-style, lit/dark string art (`_HOUSE_TILE_*`,
  `_HOUSE_SLATE_*`, `_HOUSE_THATCH_*`, `_HOUSE_STONE_*`, and the never-called
  `house_wild`/`house_scouted`/etc names) is deleted, not kept unused.
* **Trees moved out of the tile-grid batch.** `_draw_tiles` draws the *whole*
  screen's ground in one instanced call at one uniform quad size -- trying to
  give one tile kind a bigger, non-square quad inside that same call breaks
  down sideways: a wider quad bleeds into a same-row neighbour that was
  written *later* in raster order and therefore paints over it, a visible
  clip on one side that taller-only quads never hit (a row *below* is always
  written later, so "grows upward" already worked by luck of that same raster
  order). `_draw_trees` (new, called from `draw()` after `_draw_structures`)
  draws each `TREE` tile as its own `_building`-style anchored quad instead --
  `np.nonzero` on the grid window walks row-major, so a tree lower on screen
  is still queued, and drawn, after one above it, which is what keeps their
  canopies overlapping correctly without an explicit sort. `_draw_tiles`
  keeps drawing `TREE` cells as flat colour when `as_map`, since `_draw_trees`
  is only called at full detail -- forgetting that split first left the map
  with a hole everywhere a forest was.
* **Characters, from the pack's own animation code, not eyeballed.** Iris
  (`ninja_blue`) and two villager roles (`samurai_green`, `samurai_blue`) are
  cut from `content/character/*/sprite.png` via a new `CHAR_TILES` table in
  `import_tileart.py`. Which cell is which facing and which walk frame came
  from reading `system/character/sprite_character.gd`
  (`FrameDirection{RIGHT=3,DOWN=0,LEFT=2,UP=1}`, `Anim.MOVING:[0,1,2,3]`)
  rather than guessing from the art -- a fully-hooded ninja looks much the
  same from more than one side, so eyeballing it would have gotten the
  mapping wrong with no visual tell. Lumi and every NPC role the pack has no
  match for (healer, emissary, keeper, warden, wraith, lanternwright) are
  still string art -- there is no dog in this checkout.
* **The bug this pass found, and had to fix before shipping either house:**
  `pixelart.sprite_image` returned shipped art immediately once
  `bigart`/`tileart` covered a name, with **no string-art fallback recorded**
  for `house_hut`, `house_barn` or `big_tree` -- unlike every prop shipped so
  far, these names have no other source, so a missing or corrupt
  `bigart.png` would not degrade the look, it would `KeyError` out of the
  render loop the first time a room or a tree tile drew. Fixed by adding
  `_HOUSE_FALLBACK` (reusing the old single cottage) and aliasing `big_tree`
  to the old one-tile tree's rows, both in `SPRITES`.
  `test_a_missing_bigart_pack_degrades_instead_of_crashing` monkeypatches
  `bigart.tiles` to prove it.
* **Not done, still open:** buildings and trees are per-object draws now,
  which is the right call for buildings (a handful per screen) but untested
  at real forest density (a copse can be 70%+ of a screen's tiles in the
  `forest` biome, per `world.py`'s `COVER` table) -- watch for it if a session
  reports the overworld feeling slow in dense woodland; nothing in this pass
  measured frame time, only correctness. RPG Mix
  (<https://pixel-boy.itch.io/rpg-mix>, CC-BY 4.0, 80+ monsters) was the
  user's pick for the *next* source, for wildlife/beasts -- it is not a git
  repo like Ninja Adventure, so it needs a manual download into
  `junk/rpg-mix/` before anything can cut from it. Full provenance for
  everything landed here: `art/CREDITS.md`.

**Handover, 2026-08-11 (HUD and CC0 art pass).** The player-reported complaint
was that the overworld HUD sat on screen **permanently** and covered most of
the view (`gui/overworld.py::_draw_hud`) -- settled/scouted counts, loadout,
labels/bodies, mode, seal/licence and the dark-manifold flag were all drawn as
one fixed panel every frame, regardless of whether the player was reading it.
Fixed by splitting what it was doing:

* **A land banner, not a standing panel.** `_land_banner_land` /
  `_land_banner_timer` (set in `update`, drawn in `_draw_hud`) name the land
  Iris just crossed into, hold for `LAND_BANNER_SECONDS` (3.5s), then fade over
  `LAND_BANNER_FADE` and disappear. Retimed only on a genuine region change, so
  standing still does not re-arm it.
* **A `STATUS` tab**, first in `OverworldGame.TABS`, carries everything the
  panel used to show permanently -- read on request instead of blocking the
  world it describes (`_menu_rows`, the `"STATUS"` branch).
* **`the dark manifold`** is the one thing kept always-visible, now a single
  small tag in the top-right corner rather than a panel line, because it is
  the one flag that changes what the rest of the screen means. `recovering`
  moved into the existing contextual bottom band instead of a corner badge,
  next to `found <loot>` and the tutorial line -- it already had a home.
* Two tests hard-coded that the pause menu opens on the `MAP` tab
  (`test_menu_toggles_a_map_that_fits_the_world`,
  `test_the_menu_has_tabs_and_closes`); updated for `STATUS` first, plus new
  tests for the banner's arm/countdown and the STATUS tab's content.

**Also asked for: more from the CC0 packs, at native resolution, not
downscaled.** `rock` and `flowers` (`gui.pixelart.OVER_GROUND`) were the
flattest hand-drawn string art in the game -- replaced with real art from a
**second CC0 source**: ArMM1998's "Zelda-like tilesets and sprites"
(OpenGameArt, confirmed CC0 via the licence field on the listing), reached
through the already-referenced `junk/pyzelda-rpg` checkout (`graphics/test/rock.png`,
`graphics/grass/grass_3.png` -- see the pyzelda mining note below, which took
its *code*; this pass took two files of its *art*). Those files ship
**pre-upscaled 4x** with nearest-neighbour resampling for distribution
convenience; `import_tileart._load_native` undoes exactly that (stride-samples
one pixel per 4x4 block) rather than resampling a second time, which would
have blurred art that was never blurry. `PROP_SOURCE` / `PROPS` in
`build_tools/dev_utils/import_tileart.py` is the second-source sibling of the
existing `SOURCE` / `TILES`; both write into the one shipped `terrain.png`.

**The bug this actually found:** `pixelart.sprite_image` returned shipped pack
art immediately whenever `tileart.tiles()` covered a name, *before* the
prop-composites-over-ground step -- fine for plain ground fills, wrong for
`OVER_GROUND` names, because a prop with real transparency shipped that way is
a hole with nothing behind it. `test_a_prop_stands_in_real_ground_rather_than_a_hole`
existed and caught it immediately. Fixed by checking `OVER_GROUND` membership
first: a prop always composites over its ground now, whether the prop's own
art is shipped (rock, flowers) or still string art (tree, deadtree, ruin).

**Not done, and why:** trees stayed string art. Neither CC0 pack has a tree
that is one 16x16 cell -- a tree wants a canopy taller than the ground tile it
stands on, and `_draw_tiles` draws every tile-grid prop (tree/rock/flowers) as
one uniform-size numpy-batched instance, not a per-object draw call the way
buildings get (`_draw_structures`). Giving props their own size and anchor,
vectorised the same way `_draw_tiles` already is (a per-instance size array
plus a y-offset so a taller sprite's *base* stays on the tile and its canopy
grows upward) is the real follow-up -- a naive per-tile Python draw call would
reintroduce the exact "thousands of quads, one call each" perf regression the
grid batch was built to fix. Full provenance in `art/CREDITS.md`.

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

**Mined from a small pygame RPG (2026-08-11).** `junk/pyzelda-rpg`, MIT, 2,016
lines of Python. Tiny beside ZQuest and useful for different things, because it
is a *modern* game rather than a 1980s one: it has the layers ZQuest predates.

**Taken:** the whole particle and floating-text layer, as
[`chigame/particles.py`](../subsystems/chigame.md) — a rising number, an orb
that flies to a target, a one-shot burst. Engine-level, so all six games get
it; Lumis Quest uses it for damage numbers, for the impact spark (in the colour
*your* beast emits, because an impact is light arriving), and for the moment a
label comes off and visibly travels from the animal into you. `alpha` became a
Scene-level hint on the way, so anything can fade without every pack branch
learning about transparency.

**Also taken:**

1. **The notice radius** → `steering.Temper.notice`, gating homing. ZQuest has
   no equivalent: its enemies are always on. This closed a real hole rather
   than adding a nicety — *alignment has no distance in it*, so a beast forty
   tiles down your column was reacting to you through a forest it cannot see
   over, and from where the player stands that looks like nothing at all. The
   rising edge of `Drift.noticed` is surfaced as `Npc.startled` and drawn as a
   **"!"**, because "has not seen you" and "is stalking you" must not look the
   same.
2. **A\* with the recalculation *policy*** → `api/pathing.py`. Recalculate when
   the path is stale **or** when the destination has changed grid cell,
   whichever comes first, and fall back to the direct line when there is no
   path. The search is textbook; the policy is the hard-won part — on a timer
   alone a follower cuts corners into walls for half a second after its target
   turns, and every frame means the pathfinding *is* the frame. Wired into
   `agents.Society._walk`, which previously said in as many words: *"Blocked
   flat. Give up on this errand rather than grinding into a wall for the rest
   of the session."* Every errand whose destination sat behind a building was
   abandoned. Deliberately **not** used for fleeing beasts, which should look
   panicked rather than well-routed.
   One thing is ours: the search takes a **node budget**. That game's maps are
   one screen; this world is tens of thousands of tiles, and an unreachable
   goal makes an uncapped A\* expand every reachable cell — per walker, per
   recalculation.

**Found and not taken, in the order it is worth doing:**

3. **Knockback as one signed scalar**: `direction *= -resistance`, applied by
   negating the direction the hit came from.
4. **An invulnerability window with a flicker**, which is how a player learns
   that a hit registered.
5. **An `attack_radius` distinct from the notice radius**, i.e. a third state
   between wandering and engaging. Only worth it once something happens on the
   overworld other than touching a beast to start a fight.

**Skipped, with reasons:** the five-bar stat shop (stats here are photophysics
and come from which label is in which body — a shop that sells brightness would
undo the bestiary), its sprite-frame *animation* pipeline (chigame is
procedural and string-art; shipping per-frame PNG sequences would undo the
swappable look -- **note this line predates the ground and prop tile pipeline
below**, which does ship static CC0 art for individual sprites; what stayed
skipped is *animated frame sets*, not pack art generally), its axis-separated
collision (ours already sub-steps, slips corners and tests per-quadrant
solidity, so adopting it is a regression), and its save manager
(`api/save.py` already versions and migrates).

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
1. ✅ **The interiors are built, tested, and now reachable** (landed
   2026-08-11, see the top-of-file handover). `_building_scene`/`_enter_building`
   open a room on approach to any `T.ENTERABLE` tile, and `_leave_interior`
   returns her outdoors via the room's `EXIT` tile. What was *not* closed in
   that pass: interiors have furniture but no people -- `npcs.py` still only
   populates the overworld, so a house is walkable but empty. Wiring an NPC
   or two per room (a resident by the same persona seam Part 8/`api/personas.py`
   already builds for outdoor keepers) is the natural next step, not a new
   mechanism.
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
