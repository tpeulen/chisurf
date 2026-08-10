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
        "ggggg2vvvv1ggggg", "ggg1vv2VVvvvggg" + "g", "ggvv2VVVVVVvv1gg", "gvv2VVVVVVVVvvgg",
        "gv2VVVVVVVVVVvgg", "gv2VVVVVVVVvVvg" + "g", "gvVVVVVVVvVVVvgg", "gvvVVVVVVVVvvvgg",
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
        "DSSDdDSSSDdDSSSD", "SSSSdSSSSSdSSSSS", "DSSDdDSSSDdDSSSD", "dddddddddddddddd",
        "SDdDSSSDdDSSSDdS", "SSdSSSSSdSSSSSdS", "SDdDSSSDdDSSSDdS", "dddddddddddddddd",
        "DSSDdDSSSDdDSSSD", "SSSSdSSSSSdSSSSS", "DSSDdDSSSDdDSSSD", "dddddddddddddddd",
        "SDdDSSSDdDSSSDdS", "SSdSSSSSdSSSSSdS", "SDdDSSSDdDSSSDdS", "dddddddddddddddd",
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

#: Every sprite, by name. Terrain first so a tile lookup is a dict hit.
SPRITES: dict[str, list[str]] = {
    **TERRAIN,
    "house_wild": _HOUSE_DARK,
    "house_withered": _HOUSE_DARK,
    "house_scouted": _HOUSE_LIT,
    "house_settled": _HOUSE_LIT,
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
