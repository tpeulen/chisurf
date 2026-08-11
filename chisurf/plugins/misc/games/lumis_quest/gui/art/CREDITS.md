# Where this art comes from

`terrain.png` holds the world's **ground tiles**, cut from the
**Ninja Adventure Asset Pack** by **Pixel-boy** and **AAA**.

- Source: <https://github.com/pixel-boy/NinjaAdventure> (also on itch.io at
  <https://pixel-boy.itch.io/ninja-adventure-asset-pack>)
- Licence: **CC0 1.0 Universal** — a public-domain dedication. No attribution
  is required and nothing propagates into this package's own licence. It is
  given here anyway, because not being obliged to is not a reason not to.

Only the ground is theirs. Every building, character, creature and item in this
game is authored in `gui/pixelart.py` as string art and is this project's own —
a marked hare in the colour of the dye somebody fixed into it is not a thing a
generic pack has.

`terrain.json` records which cell of which sheet each tile was cut from, and
`build_tools/dev_utils/import_tileart.py` re-cuts them from a checkout of the
pack. Both exist so that the provenance of every shipped pixel is a command
anyone can re-run rather than a claim in a file.

## What was *not* taken, and why

The same reference family ships a font (`joystix.ttf`, in a different
repository that bundles this art). It is **not** CC0: its `name` table reads
`© 1996-2018 Typodermic Fonts Inc`, it carries a trademark notice, and it
grants no licence. It is not shipped here. The typeface in
`chisurf/gui/chigame/pixelfont.py` is authored in this repository.
