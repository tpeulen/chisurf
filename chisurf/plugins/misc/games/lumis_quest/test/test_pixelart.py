"""The pixel art is authored, packed and drawable.

The sprites are string art in the source, so these assert the properties that
string art can silently get wrong: a row typo that shortens a sprite, a palette
character nobody defined, an atlas whose uv rectangles do not line up with the
pixels they are supposed to address.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.misc.games.lumis_quest.gui import pixelart


def test_every_sprite_is_square_and_complete():
    """No sprite may be short a row or a column.

    A missing row is invisible in review and shows up in the game as a sprite
    with its feet cut off.
    """
    for name, rows in pixelart.SPRITES.items():
        assert len(rows) == pixelart.SIZE, f"{name} has {len(rows)} rows"
        for index, row in enumerate(rows):
            assert len(row) == pixelart.SIZE, f"{name} row {index} is {len(row)} wide"


def test_every_pixel_uses_a_defined_colour():
    """An undefined character silently renders as a transparent hole."""
    unknown: dict[str, set[str]] = {}
    for name, rows in pixelart.SPRITES.items():
        for row in rows:
            for char in row:
                if char not in pixelart.PALETTE:
                    unknown.setdefault(name, set()).add(char)
    assert not unknown, unknown


def test_iris_is_a_character_not_a_marker():
    """She has a glowing core, a body, and a sword.

    This is the whole difference between a character and a coloured dot, so it
    is worth asserting rather than eyeballing once.
    """
    for facing in ("down", "up", "right"):
        art = "".join(pixelart.SPRITES[f"iris_{facing}_0"])
        assert "c" in art or "C" in art, f"{facing}: no photon core"
        assert "t" in art or "T" in art, f"{facing}: no body"
        assert "e" in art, f"{facing}: no boots"
        assert "l" in art or "L" in art, f"{facing}: no blade"
        assert "y" in art, f"{facing}: no hilt"


def test_iris_has_a_face_only_when_facing_the_camera():
    """Her back view must not have eyes in it.

    Tested on the eye colour rather than skin: skin is also her hands, which
    are visible from behind.
    """
    front = "".join(pixelart.SPRITES["iris_down_0"])
    side = "".join(pixelart.SPRITES["iris_right_0"])
    back = "".join(pixelart.SPRITES["iris_up_0"])
    assert "i" in front, "the front view needs eyes"
    assert "i" in side, "the side view needs an eye"
    assert "i" not in back, "the back of a head has no eyes"
    # Her hands still show from behind.
    assert "s" in back


def test_lumi_is_a_dog():
    """Four legs, a snout, and a body that glows."""
    for facing in ("down", "right"):
        rows = pixelart.SPRITES[f"lumi_{facing}_0"]
        art = "".join(rows)
        assert "u" in art and "U" in art, f"{facing}: no glowing body"
        assert "p" in art, f"{facing}: no snout"
        # Legs: the bottom third has separated runs of body colour.
        legs = [row for row in rows[10:14] if "u" in row or "U" in row]
        assert legs, f"{facing}: no legs"
        runs = max(
            sum(1 for group, _ in __import__("itertools").groupby(row, key=lambda c: c in "uU")
                if group)
            for row in legs
        )
        assert runs >= 2, f"{facing}: legs are not separated"


def test_the_walk_cycle_has_two_distinct_frames():
    """A second frame identical to the first is not an animation."""
    for name in ("iris_down", "iris_up", "iris_right", "lumi_down", "lumi_right"):
        assert pixelart.SPRITES[f"{name}_0"] != pixelart.SPRITES[f"{name}_1"], name


def test_the_atlas_packs_every_sprite_where_its_uv_says():
    """A uv rectangle that misses its pixels shows the neighbouring sprite."""
    image, uvs = pixelart.build_atlas()
    assert image.shape == (pixelart.SIZE, pixelart.SIZE * len(pixelart.SPRITES), 4)
    assert set(uvs) == set(pixelart.SPRITES)

    width = image.shape[1]
    for name in pixelart.SPRITES:
        u0, v0, u1, v1 = uvs[name]
        assert 0.0 <= u0 < u1 <= 1.0 and (v0, v1) == (0.0, 1.0)
        start = int(round(u0 * width))
        packed = image[:, start:start + pixelart.SIZE]
        assert np.array_equal(packed, pixelart.sprite_image(name)), name


def test_terrain_is_dithered_rather_than_flat():
    """A single flat colour per tile is what makes generated art look generated.

    Asserted against what *ships* rather than against the authored art, so it
    still means something now that the ground comes from a tile pack.
    """
    for name in ("grass", "water", "road", "floor"):
        art = pixelart.sprite_image(name)
        colours = {tuple(pixel) for row in art for pixel in row}
        assert len(colours) >= 2, f"{name} is a flat fill"


def test_the_atlas_uploads(qapp):
    """The packed image becomes a texture the batch can bind."""
    pytest.importorskip("wgpu")
    from chisurf.gui import chigame

    try:
        device = chigame.get_device()
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    image, _ = pixelart.build_atlas()
    texture = pixelart.upload(device, image)
    assert texture.size[0] == image.shape[1]
    assert texture.size[1] == image.shape[0]


def test_the_shipped_ground_is_present_and_is_what_gets_drawn():
    """A missing art pack degrades silently, so something has to say so.

    `tileart.tiles()` returns nothing at all when the PNG is absent or will not
    decode, and the world then draws the authored string art and looks merely
    worse. That is the right runtime behaviour and the wrong thing to discover
    in a release: the failure mode of shipping without `gui/art/` is a game
    that runs.
    """
    from chisurf.plugins.misc.games.lumis_quest.gui import tileart

    shipped = tileart.tiles()
    assert shipped, "gui/art/terrain.png is missing or will not decode"
    # The ground the player spends the game walking on.
    for name in ("grass", "water", "sand", "road", "floor", "plaza"):
        assert name in shipped, name
        assert np.array_equal(pixelart.sprite_image(name), shipped[name]), name


def test_a_prop_stands_in_real_ground_rather_than_a_hole():
    """A tree is a *cell of the grid*, not a sprite over a grass cell.

    Clearing its authored backdrop without compositing leaves transparency with
    nothing beneath it -- the tree then sits in a black square, which is what
    the first attempt at this produced.
    """
    from chisurf.plugins.misc.games.lumis_quest.gui import tileart

    if "grass" not in tileart.tiles():
        pytest.skip("no shipped ground to composite against")
    for name in pixelart.OVER_GROUND:
        art = pixelart.sprite_image(name)
        # Fully transparent, not merely translucent: these sprites carry soft
        # contact shadows on purpose, and those are supposed to let the ground
        # through.
        assert (art[..., 3] > 0).all(), f"{name} has holes in it"


def test_every_shipped_tile_names_a_sprite_that_exists():
    """A tile cut under a name nothing draws is a tile nobody ever sees."""
    from chisurf.plugins.misc.games.lumis_quest.gui import tileart

    unknown = [name for name in tileart.names() if name not in pixelart.SPRITES]
    assert unknown == [], f"shipped art for sprites that do not exist: {unknown}"
