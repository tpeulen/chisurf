# Where this art comes from

Two shipped strips, cut from two CC0 sources: `terrain.png` (ground tiles,
ground-cover props, and character walk frames -- everything that is exactly
16x16) and `bigart.png` (two houses and the tree canopy -- everything that is
not).

## Ground, buildings and characters: Ninja Adventure Asset Pack

By **Pixel-boy** and **AAA**.

- Source: <https://github.com/pixel-boy/NinjaAdventure> (also on itch.io at
  <https://pixel-boy.itch.io/ninja-adventure-asset-pack>)
- Licence: **CC0 1.0 Universal** — a public-domain dedication. No attribution
  is required and nothing propagates into this package's own licence. It is
  given here anyway, because not being obliged to is not a reason not to.

What is cut from it, and by what:

- **Ground** (`build_tools/dev_utils/import_tileart.py`'s `TILES`): the
  world's terrain tiles, from `content/map/tileset_floor.png` and
  `tileset_interior_floor.png`. Coordinates were **measured, not eyeballed**
  (`--survey`: opaque, low-variance, matching opposite edges).
- **Characters** (`import_tileart.py`'s `CHAR_TILES`): villagers and
  townsfolk are `samurai_green` and `samurai_blue`. Which cell is which
  facing and which walk frame is **read from the pack's own animation code**
  (`system/character/sprite_character.gd`: `FrameDirection{RIGHT=3,DOWN=0,
  LEFT=2,UP=1}` on one axis, `Anim.MOVING:[0,1,2,3]` on the other), not
  guessed from how the art looks — a fully-hooded ninja reads much the same
  from more than one side. Iris herself was tried from `ninja_blue/sprite.png`
  and reverted: a generic hooded ninja read as a different character rather
  than as her, and the follow-up request was for her original look with a
  bigger head, not a third design — she is string art again
  (`gui/pixelart.py`'s `_IRIS_*`), redrawn head-heavy but on the same
  hair/skin/tunic/core/blade palette the pack-art attempt replaced.
- **Buildings and the tree** (`build_tools/dev_utils/import_bigart.py`'s
  `RECTS`): `house_hut` and `house_barn` from `content/map/
  tileset_village_abandoned.png`, and `big_tree` (the three-lobed canopy that
  made the ground's old one-tile tree look like a placeholder next to it) from
  the same sheet. Picked by eye and tile-aligned; there is no equivalent of
  "opaque, low-variance, seamless" for a house.

## Two ground-cover props: "Zelda-like tilesets and sprites" by ArMM1998

`rock` and `flowers` (`import_tileart.py`'s `PROPS`) are cut from
**"Zelda-like tilesets and sprites"** by **ArMM1998**, in the form they reach
this repository through: pre-cut, individual PNGs bundled with the
`pyzelda-rpg` tutorial project (MIT-licensed code, over that CC0 art; the same
checkout PRD-91 already mines for steering, pathing and the particle layer —
see `okf/prds/prd-91.md`).

- Original source: <https://opengameart.org/content/zelda-like-tilesets-and-sprites>
- Vector into this repo: <https://github.com/artemshchirov/pyzelda-rpg>
  (`graphics/test/rock.png`, `graphics/grass/grass_3.png`)
- Licence: **CC0**, per OpenGameArt's licence field for that submission —
  the same public-domain dedication as Ninja Adventure. `pyzelda-rpg`'s own
  MIT licence covers its code; it does not need to, and does not, weaken the
  art's CC0 status.

## What is still this project's own

Lumi, and every NPC role Ninja Adventure has no matching character for
(healer, emissary, keeper, warden, wraith, lanternwright), every animal and
beast, and `deadtree`/`ruin` (the dark manifold's versions of the tree and a
building) are authored in `gui/pixelart.py` as string art — a marked hare in
the colour of the dye somebody fixed into it, or a dog, is not a thing either
pack has.

`terrain.json` and `bigart.json` record where every tile or sprite was cut
from, and the two importer scripts re-cut them from a checkout of each pack.
All four exist so that the provenance of every shipped pixel is a command
anyone can re-run rather than a claim in a file.

## Fallback, not just replacement

Every shipped name still has a string-art sibling in `gui/pixelart.py`'s
`SPRITES`, reached the same way the original ground tiles were: if the shipped
pack fails to load or decode, the game degrades to the drawing that already
worked rather than crashing or going blank. See
`test_a_prop_stands_in_real_ground_rather_than_a_hole` and
`test_a_missing_bigart_pack_degrades_instead_of_crashing` in
`test/test_pixelart.py`.

## What was *not* taken, and why

The same reference family ships a font (`joystix.ttf`, in a different
repository that bundles this art). It is **not** CC0: its `name` table reads
`© 1996-2018 Typodermic Fonts Inc`, it carries a trademark notice, and it
grants no licence. It is not shipped here. The typeface in
`chisurf/gui/chigame/pixelfont.py` is authored in this repository.
