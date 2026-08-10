"""Hand-authored pixel art, packed into one atlas at load time.

The sprites are written as string art -- one character per pixel, one row per
line -- because that is the only form of pixel art that survives code review.
A binary PNG in the tree is opaque: nobody can see in a diff that a sprite
changed, let alone how. This way a change to Iris' sword is a change to two
characters on one line.

Nothing is loaded from disk. The atlas is assembled into a numpy array and
uploaded once, so the pixel-art look still ships no binary assets.

**Iris** is a character, not a marker: a glowing photon core for a body, with
head, arms, legs and a sword. **Lumi** is a dog -- a four-legged companion with
the same glow, who trots after her. Both are drawn per facing, with a two-frame
walk cycle, which is what makes them read as a 16-bit character rather than a
sliding sprite.
"""

from __future__ import annotations

import numpy as np

#: Character -> RGBA. Two tones per material, because a single flat colour is
#: what makes procedural art look procedural; a light and a dark read as form.
PALETTE: dict[str, tuple[int, int, int, int]] = {
    ".": (0, 0, 0, 0),
    # Terrain
    "g": (38, 74, 46, 255), "G": (54, 98, 58, 255), "h": (28, 58, 38, 255),
    "w": (26, 52, 96, 255), "W": (40, 78, 132, 255),
    "n": (72, 52, 34, 255), "v": (30, 76, 44, 255), "V": (46, 104, 56, 255),
    "r": (86, 88, 94, 255), "R": (118, 120, 126, 255),
    "d": (110, 94, 68, 255), "D": (138, 120, 88, 255),
    "f": (74, 70, 62, 255), "F": (92, 88, 78, 255),
    "x": (96, 92, 84, 255), "X": (132, 128, 118, 255),
    "o": (128, 92, 40, 255), "O": (166, 124, 56, 255),
    # Buildings
    "b": (108, 54, 46, 255), "B": (142, 74, 60, 255),
    "m": (120, 112, 100, 255), "M": (150, 142, 128, 255),
    "k": (70, 48, 32, 255),
    # Iris
    "s": (226, 190, 158, 255),          # skin
    "a": (54, 40, 70, 255),             # hair
    "A": (86, 66, 104, 255),
    "t": (44, 92, 118, 255),            # tunic
    "T": (66, 132, 164, 255),
    "e": (52, 40, 34, 255),             # boots
    "c": (120, 240, 250, 255),          # photon core, bright
    "C": (60, 190, 220, 255),           # photon core, rim
    "l": (198, 208, 220, 255),          # blade
    "L": (248, 252, 255, 255),          # blade highlight
    "y": (156, 116, 52, 255),           # hilt
    "i": (20, 24, 32, 255),             # eye / outline
    # Villagers: robed keepers, warm and lit
    "q": (150, 120, 70, 255), "Q": (196, 162, 96, 255),
    "z": (86, 62, 44, 255),
    # Animals
    "j": (206, 202, 190, 255), "J": (236, 234, 226, 255),
    # Beasts: dark, with a sick glow
    "N": (86, 52, 104, 255), "H": (46, 30, 56, 255),
    "P": (214, 108, 236, 255),
    # Lumi the dog
    "u": (70, 190, 110, 255),
    "U": (140, 245, 170, 255),
    "p": (24, 40, 30, 255),
}

#: Pixels per sprite. 16x16 is the era's own size for a character sprite.
SIZE = 16

_ = "................"

#: Terrain. Dithered rather than flat, so a field of grass has texture.
TERRAIN: dict[str, list[str]] = {
    "grass": [
        "gggGgggggGgggggg", "ggggggggggggGggg", "gGgggggggggggggg", "gggggggGgggggggg",
        "ggggGggggggggGgg", "gggggggggGgggggg", "gGgggggggggggggg", "ggggggggggggGggg",
        "gggGgggggggggggg", "ggggggggGggggggg", "gggggggggggGgggg", "gGgggggggggggggg",
        "gggggGggggggggGg", "ggggggggggggggpg".replace("p", "g"), "ggGggggggggggggg", "gggggggggGgggggg",
    ],
    "water": [
        "wwwwwwwwwwwwwwww", "wwwWWwwwwwwwwwww", "wwwwwwwwwwwWWwww", "wwwwwwwwwwwwwwww",
        "wwwwwwwWWwwwwwww", "wwwwwwwwwwwwwwww", "wWWwwwwwwwwwwwww", "wwwwwwwwwwwwWWww",
        "wwwwwwwwwwwwwwww", "wwwwwwwwWWwwwwww", "wwwwwwwwwwwwwwww", "wwWWwwwwwwwwwwww",
        "wwwwwwwwwwwWWwww", "wwwwwwwwwwwwwwww", "wwwwwWWwwwwwwwww", "wwwwwwwwwwwwwwww",
    ],
    "tree": [
        "ggggggggggggggpg".replace("p", "g"), "gggggvvvvvgggggg", "ggggvvVVVvvggggg", "gggvvVVVVVvvgggg",
        "gggvVVVVVVVvgggg", "ggvvVVVVVVVvvggg", "gggvVVVVVVVvgggg", "gggvvVVVVVvvgggg",
        "ggggvvVVVvvggggg", "gggggvvvvvgggggg", "ggggggnnnngggggg", "ggggggnnnngggggg",
        "gggggnnnnnngggg" + "g", "ggggghhhhhhggggg", "gggggghhhhgggggg", "gggggggggggggggg",
    ],
    "rock": [
        "gggggggggggggggg", "ggggggrrrrgggggg", "gggggrRRRRrggggg", "ggggrRRRRRRrgggg",
        "gggrRRRRRRRRrggg", "gggrRRRRRRRRrggg", "ggrRRRRRRRRRRrgg", "ggrRRRRRRRRRRrgg",
        "gggrRRRRRRRRrggg", "gggrrRRRRRRrrggg", "ggggrrrrrrrrgggg", "gggggrrrrrrggggg",
        "gggggghhhhgggggg", "gggggggggggggggg", "gggggggggggggggg", "gggggggggggggggg",
    ],
    "road": [
        "dddDdddddddDdddd", "ddddddddDddddddd", "dDdddddddddddddd", "ddddddDddddddddd",
        "ddddddddddddDddd", "dddDdddddddddddd", "ddddddddDddddddd", "dddddddddddddDdd",
        "dDdddddddddddddd", "ddddDdddddddddddd"[:16], "dddddddddDdddddd", "ddddddddddddDddd",
        "ddDddddddddddddd", "dddddddDdddddddd", "ddddddddddDddddd", "dddDdddddddddddd",
    ],
    "floor": [
        "ffffffffffffffff", "fFFFfffFFFfffFFf", "ffffffffffffffff", "fffFFFfffFFFffff",
        "ffffffffffffffff", "fFFFfffFFFfffFFf", "ffffffffffffffff", "fffFFFfffFFFffff",
        "ffffffffffffffff", "fFFFfffFFFfffFFf", "ffffffffffffffff", "fffFFFfffFFFffff",
        "ffffffffffffffff", "fFFFfffFFFfffFFf", "ffffffffffffffff", "fffFFFfffFFFffff",
    ],
    "wall": [
        "XXXXXXXXXXXXXXXX", "XxxxxxxXxxxxxxxX", "XxxxxxxXxxxxxxxX", "XXXXXXXXXXXXXXXX",
        "xxxXxxxxxxxXxxxx", "xxxXxxxxxxxXxxxx", "XXXXXXXXXXXXXXXX", "XxxxxxxXxxxxxxxX",
        "XxxxxxxXxxxxxxxX", "XXXXXXXXXXXXXXXX", "xxxXxxxxxxxXxxxx", "xxxXxxxxxxxXxxxx",
        "XXXXXXXXXXXXXXXX", "XxxxxxxXxxxxxxxX", "XxxxxxxXxxxxxxxX", "XXXXXXXXXXXXXXXX",
    ],
    "gate": [
        "XXXXXXXXXXXXXXXX", "XooooooooooooooX", "XoOOoooooooOOooX", "XooooooooooooooX",
        "XoooooooooooooOX"[:16], "XoOOoooooooOOooX", "XooooooooooooooX", "XooooooooooooooX",
        "XoOOoooooooOOooX", "XooooooooooooooX", "XooooooooooooooX", "XoOOoooooooOOooX",
        "XooooooooooooooX", "XooooooooooooooX", "XoOOoooooooOOooX", "XXXXXXXXXXXXXXXX",
    ],
    "clinic": [
        "ffffffffffffffff", "ffffffffffffffff", "fffFFFFFFFFFFfff", "ffFccccccccccFff",
        "ffFcccccccccccff", "ffFcccCCCCcccccf", "ffFcccCCCCcccccf", "ffFCCCCCCCCCCccf",
        "ffFCCCCCCCCCCccf", "ffFcccCCCCcccccf", "ffFcccCCCCcccccf", "ffFcccccccccccff",
        "ffFccccccccccFff", "fffFFFFFFFFFFfff", "ffffffffffffffff", "ffffffffffffffff",
    ],
    "bridge": [
        "wwwwwwwwwwwwwwww", "oooooooooooooooo", "OOOOOOOOOOOOOOOO", "oooooooooooooooo",
        "oooooooooooooooo", "OOOOOOOOOOOOOOOO", "oooooooooooooooo", "oooooooooooooooo",
        "OOOOOOOOOOOOOOOO", "oooooooooooooooo", "oooooooooooooooo", "OOOOOOOOOOOOOOOO",
        "oooooooooooooooo", "oooooooooooooooo", "OOOOOOOOOOOOOOOO", "wwwwwwwwwwwwwwww",
    ],
}

#: A building, drawn three times: dark (nobody has read the page), lit but
#: unconfirmed (an agent scouted it), and settled (a person vouched for it).
_HOUSE = [
    "................", ".......bb.......", "......bBBb......", ".....bBBBBb.....",
    "....bBBBBBBb....", "...bBBBBBBBBb...", "..bBBBBBBBBBBb..", ".bbbbbbbbbbbbbb.",
    "..mmmmmmmmmmmm..", "..mMMmmmmmmMMm..", "..mMMmmmmmmMMm..", "..mmmmmkkmmmmm..",
    "..mmmmmkkmmmmm..", "..mmmmmkkmmmmm..", "..hhhhhkkhhhhh..", "................",
]

#: A villager: a robed keeper standing outside the page they look after.
_VILLAGER_A = [
    "................", "................", ".....zzzzz......", "....zsssssz.....",
    "....zsisisz.....", "....zsssssz.....", ".....sssss......", "....qQQQQQq.....",
    "...qQQQQQQQq....", "...qQQQQQQQq....", "...qQQQQQQQq....", "....qQQQQQq.....",
    "....qQQQQQq.....", "....qq...qq.....", "....zz...zz.....", "................",
]
_VILLAGER_B = [
    "................", "................", ".....zzzzz......", "....zsssssz.....",
    "....zsisisz.....", "....zsssssz.....", ".....sssss......", "....qQQQQQq.....",
    "..sqQQQQQQQqs...", "...qQQQQQQQq....", "...qQQQQQQQq....", "....qQQQQQq.....",
    "....qQQQQQq.....", "....qq...qq.....", "....zz...zz.....", "................",
]

#: Townsfolk: a tunic and workaday browns -- people, not keepers.
_TOWNSFOLK_A = [
    "................", "................", ".....zzzzz......", "....zsssssz.....",
    "....zsisisz.....", "....zsssssz.....", ".....sssss......", "....dDDDDDd.....",
    "...sdDDDDDds....", "...sdDDDDDds....", "....dDDDDDd.....", "....dd...dd.....",
    "....dd...dd.....", "....ee...ee.....", "................", "................",
]
_TOWNSFOLK_B = [
    "................", "................", ".....zzzzz......", "....zsssssz.....",
    "....zsisisz.....", "....zsssssz.....", ".....sssss......", "....dDDDDDd.....",
    "...sdDDDDDds....", "....dDDDDDd.....", "....dDDDDDd.....", ".....dd.dd......",
    "....dd...dd.....", "...ee.....ee....", "................", "................",
]

#: The healer: a pale hooded robe with the recovery-glow cross on the chest.
_HEALER_A = [
    "................", "................", ".....jjjjj......", "....jsssssj.....",
    "....jsisisj.....", "....jsssssj.....", ".....sssss......", "....jJJJJJj.....",
    "...jJJcccJJj....", "...jJJcCcJJj....", "....jJcccJj.....", "....jJJJJJj.....",
    "....jJJJJJj.....", "....jj...jj.....", "....zz...zz.....", "................",
]
_HEALER_B = [
    "................", "................", ".....jjjjj......", "....jsssssj.....",
    "....jsisisj.....", "....jsssssj.....", ".....sssss......", "....jJJJJJj.....",
    "...jJJcCcJJj....", "...jJJcccJJj....", "....jJcccJj.....", "....jJJJJJj.....",
    "....jJJJJJj.....", ".....jj.jj......", "...zz.....zz....", "................",
]

#: An emissary: a hooded violet robe and a staff. One drawing serves all three
#: orders; the renderer tints it in the doctrine's colour.
_EMISSARY_A = [
    "................", "................", ".....AAAAA......", "....AsssssA.....",
    "....AsisisA.....", "....AsssssA.....", ".....sssss...L..", "....aAAAAAa..y..",
    "...aAAAAAAAa.y..", "...aAAAAAAAasy..", "...aAAAAAAAa.y..", "....aAAAAAa..y..",
    "....aAAAAAa..y..", "....aa...aa..y..", "....zz...zz.....", "................",
]
_EMISSARY_B = [
    "................", "................", ".....AAAAA......", "....AsssssA.....",
    "....AsisisA.....", "....AsssssA.....", ".....sssss...L..", "....aAAAAAa..y..",
    "...aAAAAAAAa.y..", "...aAAAAAAAasy..", "...aAAAAAAAa.y..", "....aAAAAAa..y..",
    "....aAAAAAa..y..", ".....aa.aa...y..", "...zz.....zz....", "................",
]

#: An animal: a small pale four-legged thing that crops the grass.
_ANIMAL_A = [
    "................", "................", "................", "................",
    "......jjjjjj....", ".....jJJJJJJj...", "....jJJJJJJJJj..", "...jjJJJJJJJJj..",
    "..jJiJJJJJJJJj..", "..jJJJJJJJJJj...", "...jJJJJJJJj....", "....j.j..j.j....",
    "....j.j..j.j....", "....jjj..jjj....", "................", "................",
]
_ANIMAL_B = [
    "................", "................", "................", "................",
    "......jjjjjj....", ".....jJJJJJJj...", "....jJJJJJJJJj..", "...jjJJJJJJJJj..",
    "..jJiJJJJJJJJj..", "..jJJJJJJJJJj...", "...jJJJJJJJj....", "...j..jj.j..j...",
    "..j...j..j...j..", "..jjj.j..j.jjj..", "................", "................",
]

#: A beast: dark, hunched, with a sick violet glow where a mouth should be.
_BEAST_A = [
    "................", "................", "..H..........H..", "..HH........HH..",
    "..HNH......HNH..", "..HNNHHHHHHNNH..", "..HNNNNNNNNNNH..", "..HNPNNNNNNPNH..",
    "..HNNNNNNNNNNH..", "..HNNPPPPPPNNH..", "..HNNNNNNNNNNH..", "...HNNNNNNNNH...",
    "...H.HH..HH.H...", "...H.HH..HH.H...", "................", "................",
]
_BEAST_B = [
    "................", "................", "..H..........H..", "..HH........HH..",
    "..HNH......HNH..", "..HNNHHHHHHNNH..", "..HNNNNNNNNNNH..", "..HNPNNNNNNPNH..",
    "..HNNNNNNNNNNH..", "..HNNPPPPPPNNH..", "..HNNNNNNNNNNH..", "...HNNNNNNNNH...",
    "..HH.HH..HH.HH..", "..H..HH..HH..H..", "................", "................",
]

#: Iris, per facing, two frames each. The core is a photon: her body is the
#: glow, and the limbs and sword hang off it.
_IRIS_DOWN_A = [
    "................", ".....aaaaa......", "....aAAAAAa.....", "....asssssa.....",
    "....asisisa.....", "....assssaa.....", ".....sssss......", "...ttTTTTTtt....",
    "..sttCCCCCttl...", "..s.TCcccCT.L...", "....TCcccCT.l...", "....TTTTTTyyy...",
    "....tt...tt.y...", "....tt...tt.....", "....ee...ee.....", "................",
]
_IRIS_DOWN_B = [
    "................", ".....aaaaa......", "....aAAAAAa.....", "....asssssa.....",
    "....asisisa.....", "....assssaa.....", ".....sssss......", "...ttTTTTTtt....",
    "..sttCCCCCttl...", "....TCcccCT.L...", "..s.TCcccCT.l...", "....TTTTTTyyy...",
    ".....tt.tt..y...", "....tt...tt.....", "...ee.....ee....", "................",
]
_IRIS_UP_A = [
    "................", ".....aaaaa......", "....aAAAAAa.....", "....aAAAAAa.....",
    "....aAAAAAa.....", "....aaaaaaa.....", ".....aaaaa......", "...ttTTTTTtt....",
    "..sttCCCCCttl...", "..s.TCCCCCT.L...", "....TCCCCCT.l...", "....TTTTTTyyy...",
    "....tt...tt.y...", "....tt...tt.....", "....ee...ee.....", "................",
]
_IRIS_UP_B = [
    "................", ".....aaaaa......", "....aAAAAAa.....", "....aAAAAAa.....",
    "....aAAAAAa.....", "....aaaaaaa.....", ".....aaaaa......", "...ttTTTTTtt....",
    "..sttCCCCCttl...", "....TCCCCCT.L...", "..s.TCCCCCT.l...", "....TTTTTTyyy...",
    ".....tt.tt..y...", "....tt...tt.....", "...ee.....ee....", "................",
]
_IRIS_RIGHT_A = [
    "................", ".....aaaaa......", "....aAAAAAa.....", "....asssssa.....",
    "....assisaa.....", "....asssssa.....", ".....sssss......", "....tTTTTt......",
    "...tTCCCCTts....", "...tTCcccCTs.l..", "....TCcccCT..L..", "....TTTTTTyyl...",
    "....tt..tt..y...", "....tt..tt......", "....ee..ee......", "................",
]
_IRIS_RIGHT_B = [
    "................", ".....aaaaa......", "....aAAAAAa.....", "....asssssa.....",
    "....assisaa.....", "....asssssa.....", ".....sssss......", "....tTTTTt......",
    "...tTCCCCTts....", "...tTCcccCTs.l..", "....TCcccCT..L..", "....TTTTTTyyl...",
    ".....tt.tt..y...", "....tt...tt.....", "...ee.....ee....", "................",
]

#: Lumi the dog: a four-legged companion whose body is the same kind of glow.
_LUMI_RIGHT_A = [
    "................", "................", "................", "..u.........uu..",
    ".uUu.......uUUu.", ".uUUuuuuuuuUUUu.", ".uUUUUUUUUUUUUu.", "uUUpUUUUUUUUUUu.",
    "uUpUUUUUUUUUUUu.", ".uUUUUUUUUUUUu..", "..uUUuuuuuUUUu..", "..uu.u...u.uu...",
    "...u.u...u.u....", "...uUu...uUu....", "................", "................",
]
_LUMI_RIGHT_B = [
    "................", "................", "................", "..u..........uu.",
    ".uUu........uUUu", ".uUUuuuuuuuUUUu.", ".uUUUUUUUUUUUUu.", "uUUpUUUUUUUUUUu.",
    "uUpUUUUUUUUUUUu.", ".uUUUUUUUUUUUu..", "..uUUuuuuuUUUu..", "...u.uu.uu.u....",
    "..u...u.u...u...", "..uUu.u.u.uUu...", "................", "................",
]
_LUMI_DOWN_A = [
    "................", "................", "..uu.......uu...", ".uUUu.....uUUu..",
    ".uUUUuuuuuUUUu..", "..uUUUUUUUUUu...", "..uUpUUUUUpUu...", "..uUUUUUUUUUu...",
    "...uUUUpUUUu....", "...uUUUUUUUu....", "...uUUUUUUUu....", "...uUu...uUu....",
    "...uUu...uUu....", "...uuu...uuu....", "................", "................",
]
_LUMI_DOWN_B = [
    "................", "................", "..uu.......uu...", ".uUUu.....uUUu..",
    ".uUUUuuuuuUUUu..", "..uUUUUUUUUUu...", "..uUpUUUUUpUu...", "..uUUUUUUUUUu...",
    "...uUUUpUUUu....", "...uUUUUUUUu....", "...uUUUUUUUu....", "..uUu.....uUu...",
    "..uUu.....uUu...", "..uuu.....uuu...", "................", "................",
]

#: Every sprite, by name. Terrain first so a tile lookup is a dict hit.
SPRITES: dict[str, list[str]] = {
    **TERRAIN,
    "house_wild": _HOUSE,
    "house_scouted": _HOUSE,
    "house_settled": _HOUSE,
    "iris_down_0": _IRIS_DOWN_A, "iris_down_1": _IRIS_DOWN_B,
    "iris_up_0": _IRIS_UP_A, "iris_up_1": _IRIS_UP_B,
    "iris_right_0": _IRIS_RIGHT_A, "iris_right_1": _IRIS_RIGHT_B,
    "lumi_down_0": _LUMI_DOWN_A, "lumi_down_1": _LUMI_DOWN_B,
    "lumi_right_0": _LUMI_RIGHT_A, "lumi_right_1": _LUMI_RIGHT_B,
    "villager_0": _VILLAGER_A, "villager_1": _VILLAGER_B,
    "townsfolk_0": _TOWNSFOLK_A, "townsfolk_1": _TOWNSFOLK_B,
    "healer_0": _HEALER_A, "healer_1": _HEALER_B,
    "emissary_0": _EMISSARY_A, "emissary_1": _EMISSARY_B,
    "animal_0": _ANIMAL_A, "animal_1": _ANIMAL_B,
    "beast_0": _BEAST_A, "beast_1": _BEAST_B,
}


def _render(rows: list[str]) -> np.ndarray:
    """Turn string art into an RGBA image.

    Parameters
    ----------
    rows : list of str
        One string per pixel row. Short rows are padded with transparency and
        long ones truncated, so a typo in the art cannot crash the game.

    Returns
    -------
    numpy.ndarray
        ``(SIZE, SIZE, 4)`` uint8.
    """
    image = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
    for y in range(min(len(rows), SIZE)):
        row = rows[y]
        for x in range(min(len(row), SIZE)):
            image[y, x] = PALETTE.get(row[x], (0, 0, 0, 0))
    return image


def build_atlas() -> tuple[np.ndarray, dict[str, tuple[float, float, float, float]]]:
    """Pack every sprite into one texture and report their uv rectangles.

    Sprites are laid out in a single row. A 1-pixel gap would be needed for a
    filtered sampler, but the sprite sampler is point-sampling by design, so the
    tiles can abut exactly and the uv arithmetic stays trivial.

    Returns
    -------
    tuple
        ``(image, uvs)``. ``image`` is ``(SIZE, SIZE * n, 4)`` uint8; ``uvs``
        maps a sprite name to ``(u0, v0, u1, v1)``.
    """
    names = list(SPRITES)
    atlas = np.zeros((SIZE, SIZE * len(names), 4), dtype=np.uint8)
    uvs: dict[str, tuple[float, float, float, float]] = {}
    width = SIZE * len(names)
    for index, name in enumerate(names):
        atlas[:, index * SIZE:(index + 1) * SIZE] = _render(SPRITES[name])
        uvs[name] = (index * SIZE / width, 0.0, (index + 1) * SIZE / width, 1.0)
    return atlas, uvs


def upload(device, image: np.ndarray):
    """Create a GPU texture from an atlas image.

    Parameters
    ----------
    device : wgpu.GPUDevice
        Device to allocate on.
    image : numpy.ndarray
        ``(height, width, 4)`` uint8.

    Returns
    -------
    wgpu.GPUTexture
        The uploaded atlas.
    """
    import wgpu

    height, width = image.shape[:2]
    texture = device.create_texture(
        size=(width, height, 1),
        format=wgpu.TextureFormat.rgba8unorm,
        usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
    )
    device.queue.write_texture(
        {"texture": texture},
        np.ascontiguousarray(image).tobytes(),
        {"bytes_per_row": width * 4, "rows_per_image": height},
        (width, height, 1),
    )
    return texture
