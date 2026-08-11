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
    # The 16-bit pass: a material is three tones and an edge, not a fill.
    "1": (28, 58, 36, 255),      # grass deep shade
    "2": (88, 142, 80, 255),     # grass light blade
    "3": (204, 184, 96, 255),    # meadow flower
    "4": (14, 34, 68, 255),      # water deep
    "6": (62, 112, 162, 255),    # water high
    "7": (156, 204, 232, 255),   # water sparkle
    "8": (52, 44, 34, 255),      # timber dark
    "9": (255, 214, 120, 255),   # lit window glow
    "E": (30, 27, 24, 255),      # outline / darkest edge
    "I": (176, 96, 72, 255),     # roof light
    "K": (92, 44, 40, 255),      # roof shadow
    "S": (206, 198, 184, 255),   # plaster light
    "Z": (104, 62, 30, 255),     # door wood
    "5": (10, 14, 10, 110),      # soft drop shadow
    "0": (10, 14, 10, 55),       # softer shadow edge
    # The wider overworld: shore, bog, cliff, cave, paving, tilled ground.
    ",": (214, 196, 150, 255),   # sand light
    ";": (176, 156, 112, 255),   # sand dark
    "&": (86, 102, 66, 255),     # marsh light
    "%": (58, 72, 48, 255),      # marsh dark
    "^": (146, 142, 136, 255),   # cliff face
    "@": (74, 72, 70, 255),      # cliff shadow
    "#": (16, 14, 18, 255),      # cave mouth
    "=": (150, 146, 140, 255),   # cobble light
    "-": (104, 100, 96, 255),    # cobble dark
    "+": (78, 58, 40, 255),      # tilled earth
    "*": (110, 168, 80, 255),    # sprout
    # The dark manifold: ash, tar, and the violet of a rift.
    "(": (104, 100, 104, 255),   # ash light
    ")": (62, 60, 64, 255),      # ash dark
    "[": (18, 16, 22, 255),      # tar
    "]": (44, 38, 54, 255),      # tar sheen
    "{": (96, 92, 92, 255),      # ruin stone
    "}": (52, 50, 52, 255),      # ruin shadow
    "?": (188, 120, 255, 255),   # rift
    # Premises.
    "!": (255, 226, 150, 255),   # lamp flame
    "Y": (222, 216, 204, 255),   # dressed white stone
    "$": (168, 72, 64, 255),     # awning red
    ">": (170, 190, 205, 255),   # ground glass / steel
    # More than one kind of house, because a street of twenty identical boxes
    # is a housing estate whatever you paint on it.
    "<": (112, 126, 146, 255),   # slate light
    "/": (64, 74, 94, 255),      # slate shadow
    "~": (186, 158, 96, 255),    # thatch light
    "|": (126, 102, 60, 255),    # thatch shadow
    ":": (168, 152, 126, 255),   # timber-framed wall
}

#: Pixels per sprite. 16x16 is the era's own size for a character sprite.
SIZE = 16

_ = "................"

#: Terrain, 16-bit style: every material is three tones and an edge, with two
#: variants where a repeating tile would betray the grid (grass) and two
#: frames where stillness would betray the water.
TERRAIN: dict[str, list[str]] = {
    "grass": [
        "gggGg1gggggGgggg", "g2ggggggg2gggg1g", "g2gggGgggGgg3ggg", "gggg1ggg2ggggggg",
        "gGgggg2gGgggg2gg", "gggGgggg2ggGgggg", "g1ggggggggg1gggg", "gggg2Ggggggggg1g",
        "gg2gGggg2gggGggg", "ggggggg1ggggGggg", "gGgg1ggggg2ggggg", "gggggggGg2gggg1g",
        "g2ggGgggggggGggg", "gggggg1ggGgggggg", "ggG3ggggggggg2gg", "gggggggg1ggggggg",
    ],
    "grass2": [
        "g1ggggGggggg2ggg", "gggg2ggggGgggggg", "gGgggg1ggg2ggGgg", "gg2ggggGgggggg1g",
        "ggggGggg2ggg3ggg", "g1gggg2ggggGgggg", "ggGggggggg1ggggg", "gg3ggGgg2ggggGgg",
        "gggggggggg2ggg1g", "g2gGgg1ggggggggg", "ggggggggGgg2gggg", "gGg2gggggggggGgg",
        "gggggGgg1ggg2ggg", "g2ggggggggGggggg", "gggg1ggg2ggggg3g", "ggGggggggg1ggggg",
    ],
    "water": [
        "wwww4wwwwwww4www", "ww6Wwwww4ww7Wwww", "w4ww6wwwwwwwww4w", "wwwwwww6Wwwwwwww",
        "w7W6wwwwww4wwwww", "wwwwww4wwwww6Www", "w4wwwwwwww6wwww4", "wwww6W7wwwwwwwww",
        "wwwwwwwww4www6ww", "w6wwww4wwwww7Www", "wwww6Wwwwwwwwwww", "w4wwwwwww6wwww4w",
        "wwwwww7W6wwwwwww", "ww6wwwwwww4wwwww", "w4wwww4wwwww6Www", "wwwwwwwwwwwwwwww",
    ],
    "water2": [
        "www6wwww4wwwwww4", "w4wwwww7Wwww6www", "wwww6Wwwwwwwww4w", "w7Wwwwww4ww6wwww",
        "wwwww4wwwwwwwW6w", "w6wwwwww6Wwwwwww", "wwww4wwwwwww4www", "wwwwwww6ww7Wwwww",
        "w4w6Wwwwwwwwww6w", "wwwwwww4w6wwwwww", "ww7Wwwwwwwww6Www", "wwwwww6wwww4wwww",
        "w6wwwwwwwW7wwww4", "wwww4wwwwwwww6ww", "wW6wwwww4wwwwwww", "wwwwwwwwwwwwwwww",
    ],
    "tree": [
        "ggggg2vvvv1ggggg", "ggg1vv2VVvvvgggg", "ggvv2VVVVVVvv1gg", "gvv2VVVVVVVVvvgg",
        "gv2VVVVVVVVVVvgg", "gv2VVVVVVVVvVvgg", "gvVVVVVVVvVVVvgg", "gvvVVVVVVVVvvvgg",
        "ggvvVVVvVVVvvggg", "gg1vvvVVvvvv1ggg", "gggg1vvvvv1ggggg", "gggggEnnEg1ggggg",
        "gggg1EnnEg2ggggg", "ggg55EnnE55ggggg", "gg5hhhhhhhh5gggg", "ggg55555555ggggg",
    ],
    "rock": [
        "gggggggggggggggg", "gggggg1rrr1ggggg", "gggggrRRRRr1gggg", "ggg1rRRXXRRrgggg",
        "gggrRRXXXRRRr1gg", "ggrRRXXXRRRRRrgg", "ggrRRXRRRRRrRrgg", "ggrRRRRRRrrRrggg",
        "gg1rRRRRRRRrrggg", "gggrrRRrRRrr1ggg", "gggg1rrrrrr5gggg", "ggg55rrrr55ggggg",
        "gg5hhhhhhhh5gggg", "ggg555555555gggg", "gggggggggggggggg", "gggggggggggggggg",
    ],
    "road": [
        "dddDdd1ddddDdddd", "ddDddddddnddddDd", "dddddd8dddddDddd", "dDdddddDdd1ddddd",
        "ddddnddddddddDdd", "dddDddd1dDdddddd", "dDddddddddddd8dd", "dddddDddndddDddd",
        "dd1ddddddDdddddd", "ddddDd8ddddd1ddd", "dDddddddDddddddD", "dddd1ddddddnDddd",
        "ddDdddDdd8dddddd", "dddddddddddDd1dd", "d8dDdd1ddddddddd", "ddddddddDddddndd",
    ],
    "floor": [
        "ddDddddddDdddddd", "dddddxddddddDddd", "dDddddddddxddddd", "ddddDdddddddddDd",
        "dddxdddddDdddddd", "dDdddddddddddxdd", "ddddddDdddddddDd", "dxddddddddDddddd",
        "ddDdddddxdddddDd", "ddddddDddddddddd", "dDddxdddddDddddd", "dddddddDdddxdddd",
        "ddDddddddddddDdd", "ddddxddDdddddddd", "dDdddddddxdddddd", "dddDddddddddDddd",
    ],
    "wall": [
        "SSSSSSSSSSSSSSSS", "XxxXxxxXxxxXxxxX", "XxxXxxxXxxxXxxxX", "EEEEEEEEEEEEEEEE",
        "xXxxxXxxxXxxxXxx", "xXxxxXxxxXxxxXxx", "EEEEEEEEEEEEEEEE", "XxxXxxxXxxxXxxxX",
        "XxxXxxxXxxxXxxxX", "EEEEEEEEEEEEEEEE", "xXxxxXxxxXxxxXxx", "xXxxxXxxxXxxxXxx",
        "EEEEEEEEEEEEEEEE", "XxxXxxxXxxxXxxxX", "XxxXxxxXxxxXxxxX", "EEEEEEEEEEEEEEEE",
    ],
    "gate": [
        "SSSSSSSSSSSSSSSS", "XEZZZZZZZZZZZZEX", "XEZoZZoZZoZZoZEX", "XEZZZZZZZZZZZZEX",
        "XEZZ8ZZZZZ8ZZZEX", "XEZoZZoZZoZZoZEX", "XEZZZZZZZZZZZZEX", "XEZZZ8ZZZ8ZZZZEX",
        "XEZoZZoZZoZZoZEX", "XEZZZZZZZZZZZZEX", "XEZ8ZZZZZZZ8ZZEX", "XEZoZZoZZoZZoZEX",
        "XEZZZZZZZZZZZZEX", "XEZZZ8ZZZ8ZZZZEX", "XEZoZZoZZoZZoZEX", "SSSSSSSSSSSSSSSS",
    ],
    "clinic": [
        "DSSDdDSSSDdDSSSD", "SSSSdSSSSSdSSSSS", "SSEEEEEEEEEEEESS", "SEECccccccccEESS",
        "SECcccccccccCESS", "SECccc7CCcccCESS", "SECcccCCCCccCESS", "SECC7CCCCCC7CESS",
        "SECCCCCCCC7CCESS", "SECcccCCCCccCESS", "SECccc7CccccCESS", "SECcccccccccCESS",
        "SEECccccccccEESS", "SSEEEEEEEEEEEESS", "SSdSSSSSdSSSSSdS", "dddddddddddddddd",
    ],
    "bridge": [
        "w4ww6Wwww4ww6www", "nEooOooEooOooEon", "nEOOOOOEOOOOOEOn", "nEoooooEoooooEon",
        "nEoOoooEoOoooEon", "nEoooooEoooooEon", "nEEEEEEEEEEEEEEn", "nEOoooOEOoooOEon",
        "nEoooooEoooooEon", "nEoooOoEooOooEon", "nEEEEEEEEEEEEEEn", "nEooOooEoOoooEon",
        "nEOOOOOEOOOOOEOn", "nEoooooEoooooEon", "w6ww4wwww6Ww4www", "wwww4ww6wwww4www",
    ],
}

#: The buildings: a dark cottage (nobody has read the page -- shuttered, no
#: light in the windows) and a lit one (the windows glow). State tints do the
#: rest: wild is cold, withered is a sick brown, scouted cool, settled warm.
_HOUSE_DARK = [
    "................", ".......KK.......", "......KIbK......", ".....KIbbbK.....",
    "....KIbbbbbK....", "...KIbbbbbbbK...", "..KIbbbbbbbbbK..", ".KIbbbbbbbbbbbK.",
    ".KKKKKKKKKKKKKK.", ".EmSmmmmmmmmSmE.", ".EmMEEmmmmEEMmE.", ".EmMEEmmmmEEMmE.",
    ".EmmmmmZZmmmmmE.", ".EmmmmmZZmmmmmE.", ".Emmmmm88mmmmmE.", ".55555555555555.",
]
_HOUSE_LIT = [
    "................", ".......KK.......", "......KIbK......", ".....KIbbbK.....",
    "....KIbbbbbK....", "...KIbbbbbbbK...", "..KIbbbbbbbbbK..", ".KIbbbbbbbbbbbK.",
    ".KKKKKKKKKKKKKK.", ".EmSmmmmmmmmSmE.", ".EmM99mmmm99MmE.", ".EmM99mmmm99MmE.",
    ".EmmmmmZZmmmmmE.", ".EmmmmmZ9mmmmmE.", ".Emmmmm88mmmmmE.", ".55555555555555.",
]

#: Four ways to build a house, dark and lit. A page's address picks one, so a
#: street has slate beside thatch beside tile the way a street does, and the
#: same page is the same house on every visit. Drawn full-height in the sprite
#: and rendered a tile and a half tall, which is how a 16-bit town gets
#: buildings that stand *over* the ground rather than sitting inside it.
_HOUSE_TILE_DARK = [
    "................", "......KIIK......", ".....KIIIIK.....", "....KIIIIIIK....",
    "...KIIIIIIIIK...", "..KIIIIIIIIIIK..", ".KKKKKKKKKKKKKK.", ".E::::::::::::E.",
    ".E:mm::::::mm:E.", ".E:mm::::::mm:E.", ".E::::::::::::E.", ".E:::::ZZ:::::E.",
    ".E:::::ZZ:::::E.", ".E:::::Z8:::::E.", ".EEEEEEEEEEEEEE.", ".55555555555555.",
]
_HOUSE_TILE_LIT = [
    "................", "......KIIK......", ".....KIIIIK.....", "....KIIIIIIK....",
    "...KIIIIIIIIK...", "..KIIIIIIIIIIK..", ".KKKKKKKKKKKKKK.", ".E::::::::::::E.",
    ".E:99::::::99:E.", ".E:99::::::99:E.", ".E::::::::::::E.", ".E:::::ZZ:::::E.",
    ".E:::::Z9:::::E.", ".E:::::Z8:::::E.", ".EEEEEEEEEEEEEE.", ".55555555555555.",
]
_HOUSE_SLATE_DARK = [
    "................", "...<<<<<<<<<<...", "..<<////////<<..", "..<<<<<<<<<<<<..",
    ".E::::::::::::E.", ".E:mm::::::mm:E.", ".E:mm::::::mm:E.", ".E::::::::::::E.",
    ".E<<<<<<<<<<<<E.", ".E::::::::::::E.", ".E:mm::::::mm:E.", ".E:mm::::::mm:E.",
    ".E:::::ZZ:::::E.", ".E:::::Z8:::::E.", ".EEEEEEEEEEEEEE.", ".55555555555555.",
]
_HOUSE_SLATE_LIT = [
    "................", "...<<<<<<<<<<...", "..<<////////<<..", "..<<<<<<<<<<<<..",
    ".E::::::::::::E.", ".E:99::::::99:E.", ".E:99::::::99:E.", ".E::::::::::::E.",
    ".E<<<<<<<<<<<<E.", ".E::::::::::::E.", ".E:99::::::99:E.", ".E:99::::::99:E.",
    ".E:::::ZZ:::::E.", ".E:::::Z9:::::E.", ".EEEEEEEEEEEEEE.", ".55555555555555.",
]
_HOUSE_THATCH_DARK = [
    "................", "......~~~~......", ".....~~||~~.....", "....~~||||~~....",
    "...~~||||||~~...", "..~~||||||||~~..", ".~~~~~~~~~~~~~~.", ".E::::::::::::E.",
    ".E:mm::::::mm:E.", ".E:mm::::::mm:E.", ".E::::::::::::E.", ".E:::::ZZ:::::E.",
    ".E:::::ZZ:::::E.", ".E:::::Z8:::::E.", ".EEEEEEEEEEEEEE.", ".55555555555555.",
]
_HOUSE_THATCH_LIT = [
    "................", "......~~~~......", ".....~~||~~.....", "....~~||||~~....",
    "...~~||||||~~...", "..~~||||||||~~..", ".~~~~~~~~~~~~~~.", ".E::::::::::::E.",
    ".E:99::::::99:E.", ".E:99::::::99:E.", ".E::::::::::::E.", ".E:::::ZZ:::::E.",
    ".E:::::Z9:::::E.", ".E:::::Z8:::::E.", ".EEEEEEEEEEEEEE.", ".55555555555555.",
]
_HOUSE_STONE_DARK = [
    "................", "......KKKK......", ".....KIIIIK.....", "....KIIIIIIK....",
    "...KIIIIIIIIK...", "..KKKKKKKKKKKK..", ".EmmmmmmmmmmmmE.", ".Em:mm::::mm:mE.",
    ".Em:mm::::mm:mE.", ".EmmmmmmmmmmmmE.", ".Em::::::::::mE.", ".Em::ZZZZZZ::mE.",
    ".Em::ZZZZZZ::mE.", ".Em::Z8ZZ8Z::mE.", ".EEEEEEEEEEEEEE.", ".55555555555555.",
]
_HOUSE_STONE_LIT = [
    "................", "......KKKK......", ".....KIIIIK.....", "....KIIIIIIK....",
    "...KIIIIIIIIK...", "..KKKKKKKKKKKK..", ".EmmmmmmmmmmmmE.", ".Em:99::::99:mE.",
    ".Em:99::::99:mE.", ".EmmmmmmmmmmmmE.", ".Em::::::::::mE.", ".Em::ZZZZZZ::mE.",
    ".Em::Z9999Z::mE.", ".Em::Z8ZZ8Z::mE.", ".EEEEEEEEEEEEEE.", ".55555555555555.",
]

#: How many ways a house can be built. The renderer picks by page address.
HOUSE_STYLES = 4

#: A soft ground shadow, drawn under everyone who walks. Nothing anchors a
#: sprite to the ground like the shadow it casts.
_SHADOW = [
    "................", "................", "................", "................",
    "................", "................", "................", "................",
    "................", "................", "................", "......0000......",
    "....00555500....", "...055555555 0..".replace(" ", "5"), "....00555500....", "......0000......",
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

#: The wider overworld. Shore, bog, cliff and cave mouth in the lit world; ash,
#: tar, dead wood and a rift in the dark manifold. Terrain is drawn opaque --
#: it *is* the ground -- while everything built on top of it keeps a
#: transparent background so the ground shows through.
TERRAIN_WIDE: dict[str, list[str]] = {
    "sand": [
        ",,,,;,,,,,,;,,,,", ",,;,,,,,,,,,,;,,", ",,,,,,;,,,,,,,,,", ",;,,,,,,,;,,,,,,",
        ",,,,,;,,,,,,,;,,", ",,,;,,,,,,,,,,,,", ",,,,,,,,;,,,,,,;", ",;,,,,;,,,,,,,,,",
        ",,,,,,,,,,;,,,,,", ",,,;,,,,,,,,,;,,", ",,,,,,,;,,,,,,,,", ",;,,,,,,,,,;,,,,",
        ",,,,;,,,,,,,,,,;", ",,,,,,,,,;,,,,,,", ",,;,,,,,,,,,,,,,", ",,,,,,;,,,,,;,,,",
    ],
    "marsh": [
        "%%&%%%%&%%%%%&%%", "%&%%%w%%%%&%%%%%", "%%%%%%%%&%%%w%%&", "&%%%w%%%%%%%%%%%",
        "%%%&%%%%%&%%%%%%", "%%%%%%w%%%%%&%%%", "%&%%%%%%%%%%%%w%", "%%%w%&%%%&%%%%%%",
        "%%%%%%%%w%%%%%%&", "&%%%%&%%%%%%w%%%", "%%%w%%%%%&%%%%%%", "%%%%%%&%%%%%%%&%",
        "%&%%%%%%%%w%%%%%", "%%%%w%%%&%%%%%%%", "%%&%%%%%%%%%&%%%", "%%%%%%w%%%%%%%%%",
    ],
    "cliff": [
        "^^^^^^^^^^^^^^^^", "^@^^^^@^^^^^^@^^", "^^^^@^^^^^@^^^^^", "@^^^^^^^@^^^^^@^",
        "^^^@^^^^^^^^@^^^", "^^^^^^@^^^^^^^^^", "@^^^^^^^^^@^^^@^", "^^^@^^^^^^^^^^^^",
        "^^^^^^^^@^^^^^^^", "^@^^^^^^^^^^@^^^", "^^^^^@^^^^^^^^^^", "@^^^^^^^@^^^^^@^",
        "^^^@^^^^^^^^^@^^", "@@@@@@@@@@@@@@@@", "@@@@@@@@@@@@@@@@", "5555555555555555",
    ],
    "cave": [
        "^^^^^^^^^^^^^^^^", "^@^^^^^^^^^^@^^^", "^^^^^@^^^^^^^^^^", "^^^^#######^^^^^",
        "^^^#########^^^^", "^^^#########^^^^", "^^^#########^^^^", "^^^#########^^^^",
        "^^^#########^^^^", "^^^#########^^^^", "^^^#########^^^^", "^^^#########^^^^",
        "^^^#########^^^^", "@@@#########@@@@", "@@@#########@@@@", "5555555555555555",
    ],
    "plaza": [
        "==-==-==-==-==-=", "==-==-==-==-==-=", "----------------", "=-==-==-==-==-==",
        "=-==-==-==-==-==", "----------------", "==-==-==-==-==-=", "==-==-==-==-==-=",
        "----------------", "=-==-==-==-==-==", "=-==-==-==-==-==", "----------------",
        "==-==-==-==-==-=", "==-==-==-==-==-=", "----------------", "=-==-==-==-==-==",
    ],
    "garden": [
        "++++++++++++++++", "+*+++*++++*++++*", "++++++++++++++++", "++++++++++++++++",
        "+++*++++*+++*+++", "++++++++++++++++", "++++++++++++++++", "*++++*+++*+++++*",
        "++++++++++++++++", "++++++++++++++++", "++*+++++*++++*++", "++++++++++++++++",
        "++++++++++++++++", "+*+++*++++*+++++", "++++++++++++++++", "++++++++++++++++",
    ],
    "flowers": [
        "gggGg3gggggGgggg", "g2gggggg73ggggg1", "g2gggGg3gGgg3ggg", "gggg1ggg2gggg7gg",
        "gGgg3g2gGgggg2gg", "gggGgggg2ggGg3gg", "g1ggg7gggggg1ggg", "gggg2Gg3gggggg1g",
        "gg2gGggg2gg3Gggg", "ggg7gggg1gggGggg", "gGgg1ggggg2ggg3g", "gggg3ggGg2gggg1g",
        "g2ggGggg7ggggGgg", "gg3gg1ggGggggggg", "ggG3ggggggg7g2gg", "ggggg3gg1ggggggg",
    ],
    "dock": [
        "w4ww6Wwww4ww6www", "oOooOooOooOooOoo", "EEEEEEEEEEEEEEEE", "oOooOooOooOooOoo",
        "oooOooooOoooOooo", "EEEEEEEEEEEEEEEE", "oOooOooOooOooOoo", "oooOooooOoooOooo",
        "EEEEEEEEEEEEEEEE", "oOooOooOooOooOoo", "oooOooooOoooOooo", "EEEEEEEEEEEEEEEE",
        "oOooOooOooOooOoo", "oooOooooOoooOooo", "w6ww4wwww6Ww4www", "wwww4ww6wwww4www",
    ],
    "ash": [
        "(())((((()((((((", "(((()((((())((((", "()(((((()((((()(", "((((())(((((((((",
        "(()((((((((()(((", "((((()(((()(((((", "()((((((((((()((", "(((()(((()((((((",
        "((()((((((((((()", "(((((()((((()(((", "()((((((()((((((", "((((()((((((()((",
        "(()(((((((((((((", "((((((()((()((((", "()((((((((((((((", "(((()(((((()((((",
    ],
    "tar": [
        "[[[][[[[[][[[[[]", "[[][[[[[[[[[][[[", "[[[[[][[[[[[[[[[", "[][[[[[[][[[[[[[",
        "[[[[[[[][[[[][[[", "[[][[[[[[[[[[[[]", "[[[[][[[[[[[[[[[", "[][[[[[[[[[][[[[",
        "[[[[[[][[[[[[[[[", "[[][[[[[[][[[[[[", "[[[[[[[[[[[[][[[", "[][[[[][[[[[[[[[",
        "[[[[[[[[[[[[[[][", "[[[][[[[[[[[[[[[", "[[[[[[[[][[[[][[", "[[[[[[[[[[[[[[[[",
    ],
    "deadtree": [
        "(((((()((()((()(", "((((n(((n(((((((", "(((((n((n(((((((", "((((((nnn(((((((",
        "(((n(((n((n(((((", "((((nn(n(nn(((((", "((((((nnn(((((((", "(((((((n((((((((",
        "((((((Enn(((((((", "((((((Enn(((((((", "((((((Enn(((((((", "((((((Enn(((((((",
        "(((((EEnnE((((((", "((((5EnnE5((((((", "(((5))))))5(((((", "(((55555555(((((",
    ],
    "ruin": [
        "((((((((((((((((", "(({{(((((((({{((", "(({}{((((((({}{(", "(({}{{(((((({}{(",
        "(({}}{{((((({}{(", "(({}{}{{((({{}{(", "(({}{}{}{{{}}}{(", "(({}}}{}{}{}{}{(",
        "(({}{}{}{}{}{}{(", "(({}{}{}{}{}{}{(", "(({}{}{}{}{}{}{(", "(({}{}{}{}{}{}{(",
        "(({}{}{}{}{}{}{(", "(({}}}}}}}}}}}{(", "((5}}}}}}}}}}}5(", "(((55555555555((",
    ],
    "rift": [
        "[[[[[[[[[[[[[[[[", "[[[[[[[?[[[[[[[[", "[[[[[[?P?[[[[[[[", "[[[[[[?P?[[[[[[[",
        "[[[[[?PPP?[[[[[[", "[[[[?P???P?[[[[[", "[[[[?P?c?P?[[[[[", "[[[?P?cccc?P[[[[",
        "[[[?P?cccc?P[[[[", "[[[[?P?c?P?[[[[[", "[[[[?P???P?[[[[[", "[[[[[?PPP?[[[[[[",
        "[[[[[[?P?[[[[[[[", "[[[[[[?P?[[[[[[[", "[[[[[[[?[[[[[[[[", "[[[[[[[[[[[[[[[[",
    ],
}

#: Indoors. A building is one tile outside and a room when you are in it, and
#: the room has to look like somewhere somebody lives -- boards underfoot, a
#: fire, a bed, shelves with things on them.
INDOORS: dict[str, list[str]] = {
    "boards": [
        "oOoooOooooOoooOo", "oooooooooooooooo", "EEEEEEEEEEEEEEEE", "ooOoooooOoooooOo",
        "oooooooooooooooo", "oOooooOoooooOooo", "EEEEEEEEEEEEEEEE", "ooooOoooooOooooo",
        "oOoooooooOoooooO", "oooooooooooooooo", "EEEEEEEEEEEEEEEE", "oOooooOoooooOooo",
        "oooooooooooooooo", "ooOoooooOoooooOo", "EEEEEEEEEEEEEEEE", "oooOooooooOooooo",
    ],
    "iwall": [
        "EEEEEEEEEEEEEEEE", "S::::::::::::::S", "S::::::::::::::S", "S::::::::::::::S",
        "EEEEEEEEEEEEEEEE", "::::::::::::::SS", "::::::::::::::SS", "::::::::::::::SS",
        "EEEEEEEEEEEEEEEE", "S::::::::::::::S", "S::::::::::::::S", "S::::::::::::::S",
        "EEEEEEEEEEEEEEEE", "8888888888888888", "8888888888888888", "5555555555555555",
    ],
    "counter": [
        "................", "EEEEEEEEEEEEEEEE", "EOOOOOOOOOOOOOOE", "EOOOOOOOOOOOOOOE",
        "EEEEEEEEEEEEEEEE", "EooooooooooooooE", "Eo8oooooo8oooooE",
        "EooooooooooooooE",
        "EooooooooooooooE", "Eo8oooooo8oooooE",
        "EooooooooooooooE", "EooooooooooooooE",
        "EEEEEEEEEEEEEEEE", "5555555555555555", "................", "................",
    ],
    "table": [
        "................", "..EEEEEEEEEEEE..", ".EOOOOOOOOOOOOE.", ".EOOOOOOOOOOOOE.",
        ".EOoooooooooOOE.", ".EOoooooooooOOE.", ".EOOOOOOOOOOOOE.", "..EEEEEEEEEEEE..",
        "....E8....8E....", "....E8....8E....", "....E8....8E....", "....E8....8E....",
        "....EE....EE....", "....55....55....", "................", "................",
    ],
    "bed": [
        "................", ".EEEEEEEEEEEEEE.", ".E8888888888888.", ".ESSSSSSSSSS88E.",
        ".ESSSSSSSSSS88E.", ".EJJJJJJJJJS88E.", ".EJJJJJJJJJS88E.", ".EJJJJJJJJJS88E.",
        ".EJJJJJJJJJS88E.", ".EJJJJJJJJJS88E.", ".EJJJJJJJJJS88E.", ".E8888888888888.",
        ".EEEEEEEEEEEEEE.", ".55555555555555.", "................", "................",
    ],
    "shelf": [
        "................", "EEEEEEEEEEEEEEEE", "E88888888888888E", "EOoOoOoOoOoOoOoE",
        "EEEEEEEEEEEEEEEE", "E88888888888888E", "E$O$OO$O$OO$O$OE", "EEEEEEEEEEEEEEEE",
        "E88888888888888E", "EOoO$OoOoO$OoOoE", "EEEEEEEEEEEEEEEE", "E88888888888888E",
        "EEEEEEEEEEEEEEEE", "5555555555555555", "................", "................",
    ],
    "hearth": [
        "................", "EEEEEEEEEEEEEEEE", "EmMmMmMmMmMmMmME", "EmmmmmmmmmmmmmmE",
        "EmEEEEEEEEEEEEmE", "EmE##########EmE", "EmE###!!!!###EmE", "EmE##!9999!##EmE",
        "EmE#!999999!#EmE", "EmE#!9!!99!!#EmE", "EmE##!9999!##EmE", "EmE###!!!!###EmE",
        "EmEEEEEEEEEEEEmE", "EmMmMmMmMmMmMmME", "EEEEEEEEEEEEEEEE", "5555555555555555",
    ],
    "altar": [
        "................", "................", "..EEEEEEEEEEEE..", "..EYYYYYYYYYYE..",
        "..EY99999999YE..", "..EY9!!!!!!9YE..", "..EY9!9999!9YE..", "..EY9!9999!9YE..",
        "..EY9!!!!!!9YE..", "..EY99999999YE..", "..EYYYYYYYYYYE..", "..EEEEEEEEEEEE..",
        "..EYYYYYYYYYYE..", "..EEEEEEEEEEEE..", "..5555555555 5..".replace(" ", "5"), "................",
    ],
    "rug": [
        "oOoooOooooOoooOo", ".$$$$$$$$$$$$$$.", ".$OOOOOOOOOOOO$.", ".$O$$$$$$$$$$O$.",
        ".$O$OOOOOOOO$O$.", ".$O$O$$$$$$O$O$.", ".$O$O$OOOO$O$O$.", ".$O$O$OOOO$O$O$.",
        ".$O$O$$$$$$O$O$.", ".$O$OOOOOOOO$O$.", ".$O$$$$$$$$$$O$.", ".$OOOOOOOOOOOO$.",
        ".$$$$$$$$$$$$$$.", "oOoooooOoooooOoo", "oooooooooooooooo", "EEEEEEEEEEEEEEEE",
    ],
    "anvil": [
        "................", "................", "...EEEEEEEEEE...", "..EXXXXXXXXXXE..",
        "..EXxxxxxxxxXE..", "...EXxxxxxxXE...", "....EXxxxxXE....", ".....EXxxXE.....",
        ".....EXxxXE.....", "....EXxxxxXE....", "...EXxxxxxxXE...", "..EXXXXXXXXXXE..",
        "..EEEEEEEEEEEE..", "...8888888888...", "...5555555555...", "................",
    ],
    "barrel": [
        "................", "...EEEEEEEEEE...", "..EOOOOOOOOOOE..", "..EOoOoOoOoOOE..",
        "..EEEEEEEEEEEE..", "..EoooooooooOE..", "..EoooooooooOE..", "..EEEEEEEEEEEE..",
        "..EoooooooooOE..", "..EoooooooooOE..", "..EEEEEEEEEEEE..", "..EOoOoOoOoOOE..",
        "..EOOOOOOOOOOE..", "...EEEEEEEEEE...", "...5555555555...", "................",
    ],
    "exit": [
        "oOoooOooooOoooOo", "oooooooooooooooo", "EEEEEEEEEEEEEEEE", "ooOoooooOoooooOo",
        "................", "..EEEEEEEEEEEE..", "..E##########E..", "..E##########E..",
        "..E##########E..", "..E##########E..", "..E##########E..", "..E##########E..",
        "..E##########E..", "..E##########E..", "..EEEEEEEEEEEE..", "................",
    ],
}

#: What a settlement is made of. All transparent-backed: they are built *on*
#: ground the renderer has already drawn, so a tavern on cobble and a tavern on
#: grass are one sprite.
STRUCTURES: dict[str, list[str]] = {
    "well": [
        "................", "....KKKKKKKK....", "...KIIIIIIIIK...", "..KIIIIIIIIIIK..",
        "....M......M....", "....M......M....", "...mMMMMMMMMm...", "..mMMMMMMMMMMm..",
        "..mM44444444Mm..", "..mM46666664Mm..", "..mM47777774Mm..", "..mM46666664Mm..",
        "..mM44444444Mm..", "..mMMMMMMMMMMm..", "...5555555555...", "................",
    ],
    "tavern": [
        "................", "......KKKK......", ".....KIbbK......", "....KIbbbbK.....",
        "...KIbbbbbbK....", "..KIbbbbbbbbK...", ".KKKKKKKKKKKKKK.", ".EmSmmmmmmmSmmE.",
        ".$$$$$$$$$$$$$$.", ".Em99mmmmm99mmE.", ".Em99mmmmm99mmE.", ".EmmmmmZZmmmmmE.",
        ".EmmO!OZ9mmmmmE.", ".EmmmmmZZmmmmmE.", ".Emmmmm88mmmmmE.", ".55555555555555.",
    ],
    "shop": [
        "................", "................", ".....KKKKKKK....", "....KIbbbbbbK...",
        "...KIbbbbbbbbK..", "..KKKKKKKKKKKKK.", ".$Y$Y$Y$Y$Y$Y$Y.", ".EmSmmmmmmmSmmE.",
        ".Em99mmmmm99mmE.", ".EmmmmmmmmmmmmE.", ".EooOmmmmmmZZmE.", ".EoOomooOoZ9ZmE.",
        ".EooOmoOooZZZmE.", ".EmmmmmmmmZZmmE.", ".Emmmmmmmm88mmE.", ".55555555555555.",
    ],
    "smithy": [
        "................", "...EE...........", "...EE...KKKK....", "...EE..KIbbbK...",
        "...EE.KIbbbbbK..", "..KKKKKKKKKKKKK.", ".KIbbbbbbbbbbbK.", ".EmmmmmmmmmmmmE.",
        ".Emm!!mmmmmmmmE.", ".Em!99!mmmZZmmE.", ".Emmmmmmmm99mmE.", ".EmmEEEmmmZZmmE.",
        ".EmE>>>Emm88mmE.", ".EmmEEEmmmmmmmE.", ".Emmm8mmmmmmmmE.", ".55555555555555.",
    ],
    "shrine": [
        "................", "....YYYYYYYY....", "...YYYYYYYYYY...", "..YY::::::::YY..",
        "..YY:......:YY..", "..YY:.!!!!.:YY..", "..YY:.!99!.:YY..", "..YY:.!99!.:YY..",
        "..YY:.!!!!.:YY..", "..YY:......:YY..", "..YY:......:YY..", "..YY::::::::YY..",
        "..YYYYYYYYYYYY..", ".YYYYYYYYYYYYYY.", ".EEEEEEEEEEEEEE.", ".55555555555555.",
    ],
    "hall": [
        "................", "....$......$....", "....$......$....", "...KKKKKKKKKK...",
        "..KIIIIIIIIIIK..", ".KIIIIIIIIIIIIK.", "KKKKKKKKKKKKKKKK", "EYYYYYYYYYYYYYYE",
        "EY99YYYYYY99YYYE", "EY99YYYYYY99YYYE", "EYYYYYYYYYYYYYYE", "EYYYYZZZZZZYYYYE",
        "EYYYZZ9999ZZYYYE", "EYYYZZZZZZZZYYYE", "EEEEEEEEEEEEEEEE", "5555555555555555",
    ],
    "lantern": [
        "................", "................", "......EEEE......", ".....E!!!!E.....",
        ".....E9!!9E.....", ".....E9999E.....", ".....E!99!E.....", "......EEEE......",
        ".......88.......", ".......88.......", ".......88.......", ".......88.......",
        ".......88.......", "......E88E......", "......5555......", "................",
    ],
    "sign": [
        "................", "................", "...EEEEEEEEEE...", "...E88888888E...",
        "...E8SSSSSS8E...", "...E8SSSSSS8E...", "...E8SSSSSS8E...", "...E88888888E...",
        "...EEEEEEEEEE...", ".......88.......", ".......88.......", ".......88.......",
        ".......88.......", "......E88E......", "......5555......", "................",
    ],
    "fence": [
        "................", "................", "..8..........8..", "..8..........8..",
        "888888888888888E", "888888888888888E", "..8..........8..", "..8..........8..",
        "888888888888888E", "888888888888888E", "..8..........8..", "..8..........8..",
        "..8..........8..", "..E..........E..", "..55........55..", "................",
    ],
    "stall": [
        "................", "................", "..EEEEEEEEEEEE..", "..$Y$Y$Y$Y$Y$$..",
        "..$Y$Y$Y$Y$Y$$..", "..EEEEEEEEEEEE..", "..8..........8..", "..8..O..O.O..8..",
        "..8.oOo.oOoOo8..", "..888888888888..", "..8..........8..", "..8..........8..",
        "..8..........8..", "..E..........E..", "..5555555555555.", "................",
    ],
}

#: The bodies. Drawn pale and neutral on purpose: a marked animal is *tinted*
#: by the emission of whatever is fixed into it, so one hare sprite is a
#: Verdant Hare and a Garnet Hare and an Umbral Hare. That is the whole premise
#: of the bestiary made visible -- the animal is the animal, and the colour is
#: somebody else's doing.
CREATURES: dict[str, list[str]] = {
    "hare": [
        "................", "....j......j....", "...jJj....jJj...", "...jJj....jJj...",
        "...jJj....jJj...", "....jJj..jJj....", "....jJJjjJJj....", "...jJiJJJJiJj...",
        "..jJJJJJJJJJJj..", "..jJJJJJJJJJJj..", "...jJJJJJJJJj...", "....jJJJJJJj....",
        "....j.jj.jj.j...", "....j..j..j.j...", "....jj.jj.jj....", "................",
    ],
    "fox": [
        "................", "................", "..............j.", ".jj..........jJj",
        ".jJj........jJJj", ".jJJjjjjjjjjJiJj", ".jJJJJJJJJJJJJJj", "..jJJJJJJJJJJJJj",
        "..jJJJJJJJJJJJj.", "...jJJJJJJJJJj..", "...jJj..jj.jJj..", "...jJj..jj.jJj..",
        "...jjj..jj.jjj..", "................", "................", "................",
    ],
    "boar": [
        "................", "................", "...jj.......jj..", "..jJJjjjjjjjJJj.",
        ".jJJJJJJJJJJJJJj", "jJJiJJJJJJJJJJJj", "jJJJJJJJJJJJJJJj", "jJjJJJJJJJJJJJJj",
        "jJJJJJJJJJJJJJJj", "jJJJJJJJJJJJJJJj", ".jJJJJJJJJJJJJj.", "..jjJj.jj.jJjj..",
        "...jJj.jj.jJj...", "...jJj.jj.jJj...", "...jjj.jj.jjj...", "................",
    ],
    "moth": [
        "................", "......jjjj......", "....jJJJJJJj....", "..jJJJJJJJJJJj..",
        ".jJJJJjiijJJJJj.", "jJJJJJjJJjJJJJJj", "jJJJJJjJJjJJJJJj", "jJJJJJjJJjJJJJJj",
        ".jJJJJjJJjJJJJj.", "..jJJJjJJjJJJj..", "...jJJjJJjJJj...", "....jJjJJjJj....",
        ".....jjJJjj.....", "......jJJj......", "......j..j......", "................",
    ],
    "heron": [
        "................", ".........jjj....", "........jJiJj...", "........jJJJjjjj",
        ".........jJJj...", ".........jJj....", ".........jJj....", "......jjjjJj....",
        "....jJJJJJJj....", "...jJJJJJJJJj...", "..jJJJJJJJJJj...", "...jJJJJJJJj....",
        "....jJj.jJj.....", "....jJj.jJj.....", "....jjj.jjj.....", "................",
    ],
    "crow": [
        "................", "................", "......jjjj......", ".....jJiJJj.jj..",
        "....jJJJJJJjJJj.", "...jJJJJJJJJJJj.", "..jJJJJJJJJJJJj.", "..jJJJJJJJJJJj..",
        "..jJJJJJJJJJj...", "...jJJJJJJJj....", "....jJJJJJj.....", ".....jJJJj......",
        ".....j.j.j......", ".....j.j.j......", ".....jjj.jj.....", "................",
    ],
    "newt": [
        "................", "................", "................", "....jjjj........",
        "...jJiJJj.......", "..jJJJJJJjjjj...", ".jJJJJJJJJJJJj..", ".jJJJJJJJJJJJJj.",
        "..jJJJJJJJJJJJJj", "..jj.jj...jj.j..", "..j..j.....j.j..", "................",
        "................", "................", "................", "................",
    ],
    "beetle": [
        "................", "................", "......jjjj......", ".....jJiiJj.....",
        "j...jJJJJJJj...j", ".j.jJJJJJJJJj.j.", "..jJJJJJJJJJJj..", ".jJJJJJJJJJJJJj.",
        "jJJJJJjJJjJJJJJj", "jJJJJJjJJjJJJJJj", "jJJJJJjJJjJJJJJj", ".jJJJJjJJjJJJJj.",
        "..jJJJJJJJJJJj..", "...jJJJJJJJJj...", "..j.j.j..j.j.j..", "................",
    ],
    "bat": [
        "................", "................", "..jj........jj..", ".jJJj..jj..jJJj.",
        "jJJJJjjJiJjjJJJJ", "jJJJJJJJJJJJJJJj", "jJJJJJJJJJJJJJJj", ".jJJJJJJJJJJJJj.",
        "..jJJJJJJJJJJj..", "...jJJJJJJJJj...", "....jJJJJJJj....", ".....jJJJJj.....",
        "......jJJj......", "......j..j......", "................", "................",
    ],
    "jelly": [
        "................", "......jjjj......", "....jJJJJJJj....", "...jJJJJJJJJj...",
        "..jJJJJJJJJJJj..", "..jJJJJJJJJJJj..", "..jJJJJJJJJJJj..", "..jJJJJJJJJJJj..",
        "...jjjjjjjjjj...", "...j.j.j.j.j....", "...j.j.j.j.j.j..", "..j..j.j.j..j...",
        "..j..j...j..j...", ".j...j...j...j..", ".j...j...j......", "................",
    ],
    "serpent": [
        "................", "................", "....jjjjjj......", "...jJJJJJJj.....",
        "..jJJjjjjJJj....", "..jJj....jJj....", "..jJj...jJJj....", "..jJj..jJJj.....",
        "..jJj.jJJj......", "..jJjjJJj.......", "..jJJJJj........", "..jJiJj.........",
        "...jjj..........", "................", "................", "................",
    ],
    "fish": [
        "................", "................", "................", "..........jj....",
        ".....jjjjjjJJj..", "...jJJJJJJJJJJj.", "..jJiJJJJJJJJJJj", "..jJJJJJJJJJJJJj",
        "..jJJJJJJJJJJJJj", "...jJJJJJJJJJJj.", ".....jjjjjjJJj..", "..........jj....",
        "................", "................", "................", "................",
    ],
}

#: Which drawing stands in for a body that has none of its own. A silhouette
#: family beats a wrong-shaped placeholder: a vole drawn as a hare still reads
#: as a small quick thing, which is what the player needs to know.
CREATURE_FAMILY: dict[str, str] = {
    "hare": "hare", "vole": "hare", "shrew": "hare", "rat": "hare",
    "fox": "fox", "otter": "fox", "cat": "fox", "dog": "fox", "sheep": "fox",
    "boar": "boar",
    "moth": "moth", "mantis": "moth",
    "beetle": "beetle",
    "heron": "heron", "goose": "heron",
    "crow": "crow", "owl": "crow",
    "newt": "newt", "toad": "newt", "olm": "newt",
    "carp": "fish", "eel": "serpent", "adder": "serpent",
    "bat": "bat",
    "jelly": "jelly", "coral": "jelly", "anemone": "jelly",
}


def creature_sprite(species_key: str) -> str:
    """Which sprite draws a body.

    Parameters
    ----------
    species_key : str
        A key of :data:`..api.bestiary.BY_KEY`.

    Returns
    -------
    str
        A name in :data:`SPRITES`.
    """
    return f"body_{CREATURE_FAMILY.get(species_key, 'hare')}"


#: Every sprite, by name. Terrain first so a tile lookup is a dict hit.
SPRITES: dict[str, list[str]] = {
    **TERRAIN,
    **TERRAIN_WIDE,
    **INDOORS,
    **STRUCTURES,
    **{f"body_{name}": rows for name, rows in CREATURES.items()},
    "house_wild": _HOUSE_DARK,
    "house_withered": _HOUSE_DARK,
    "house_scouted": _HOUSE_LIT,
    "house_settled": _HOUSE_LIT,
    **{f"house{index}_dark": rows for index, rows in enumerate(
        (_HOUSE_TILE_DARK, _HOUSE_SLATE_DARK, _HOUSE_THATCH_DARK, _HOUSE_STONE_DARK))},
    **{f"house{index}_lit": rows for index, rows in enumerate(
        (_HOUSE_TILE_LIT, _HOUSE_SLATE_LIT, _HOUSE_THATCH_LIT, _HOUSE_STONE_LIT))},
    "shadow": _SHADOW,
    "iris_down_0": _IRIS_DOWN_A, "iris_down_1": _IRIS_DOWN_B,
    "iris_up_0": _IRIS_UP_A, "iris_up_1": _IRIS_UP_B,
    "iris_right_0": _IRIS_RIGHT_A, "iris_right_1": _IRIS_RIGHT_B,
    "lumi_down_0": _LUMI_DOWN_A, "lumi_down_1": _LUMI_DOWN_B,
    "lumi_right_0": _LUMI_RIGHT_A, "lumi_right_1": _LUMI_RIGHT_B,
    # The dim hound waiting in the grass is drawn through the NPC path, which
    # names sprites by kind: these alias the down-facing frames.
    "lumi_0": _LUMI_DOWN_A, "lumi_1": _LUMI_DOWN_B,
    "villager_0": _VILLAGER_A, "villager_1": _VILLAGER_B,
    "townsfolk_0": _TOWNSFOLK_A, "townsfolk_1": _TOWNSFOLK_B,
    "healer_0": _HEALER_A, "healer_1": _HEALER_B,
    "emissary_0": _EMISSARY_A, "emissary_1": _EMISSARY_B,
    "animal_0": _ANIMAL_A, "animal_1": _ANIMAL_B,
    "beast_0": _BEAST_A, "beast_1": _BEAST_B,
    # Premises keepers are townsfolk with a counter in front of them; a Warden
    # is the robed-and-staffed figure, tinted gold by the renderer; a wraith is
    # the old beast drawing, which is exactly right -- it is the shape of
    # something that used to be an animal.
    "keeper_0": _TOWNSFOLK_A, "keeper_1": _TOWNSFOLK_B,
    "warden_0": _EMISSARY_A, "warden_1": _EMISSARY_B,
    "wraith_0": _BEAST_A, "wraith_1": _BEAST_B,
    "lanternwright_0": _EMISSARY_A, "lanternwright_1": _EMISSARY_B,
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
