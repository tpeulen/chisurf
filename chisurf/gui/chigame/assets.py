"""The AssetPack seam — how a game's meaning becomes a look and a sound.

Games emit *semantic* draw calls and never name a colour, a texture or a shader::

    scene.draw("dye", "atto488", state="idle", at=(x, y))

An :class:`AssetPack` resolves ``("dye", "atto488", "idle")`` into something
drawable. :class:`ProceduralPack` ships as the default and needs no image files
at all: it renders signed-distance shapes, and a fluorophore's colour is derived
from its real emission maximum rather than chosen. A pack backed by a sprite
atlas can replace it later without a line of game code changing.

Music belongs to the pack too, deliberately: a look and its score are one
artistic decision, so swapping the pack swaps both.
"""

from __future__ import annotations

import dataclasses

from .render import ELLIPSE, GLOW, RECT, RING, ROUND, TRI


@dataclasses.dataclass
class Appearance:
    """How one semantic thing is drawn.

    Attributes
    ----------
    shape : float
        A shape constant from :mod:`chisurf.gui.chigame.render`.
    color : tuple of float
        sRGB RGBA in 0..1.
    param : float
        Shape parameter — corner radius, ring inner radius, glow falloff.
    softness : float
        Edge softness in local units.
    scale : float
        Multiplier applied to the size the game asked for, letting a pack make
        a creature read larger than its logical footprint.
    uv : tuple of float
        Atlas rectangle. Meaningful only for a textured pack.
    """

    shape: float = RECT
    color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    param: float = 0.0
    softness: float = 0.02
    scale: float = 1.0
    uv: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)


def wavelength_to_srgb(nanometres: float) -> tuple[float, float, float]:
    """Convert a visible wavelength to an approximate sRGB colour.

    This is the art direction of the default pack: a fluorophore is drawn in the
    colour it actually emits, so the palette is data rather than taste and the
    picture teaches spectra. Wavelengths outside the visible range clamp to the
    nearest visible end rather than fading to black, because an invisible
    creature is a bug, not a feature.

    Parameters
    ----------
    nanometres : float
        Wavelength in nm.

    Returns
    -------
    tuple of float
        sRGB components in 0..1.
    """
    w = float(min(max(nanometres, 380.0), 780.0))
    if w < 440.0:
        r, g, b = -(w - 440.0) / 60.0, 0.0, 1.0
    elif w < 490.0:
        r, g, b = 0.0, (w - 440.0) / 50.0, 1.0
    elif w < 510.0:
        r, g, b = 0.0, 1.0, -(w - 510.0) / 20.0
    elif w < 580.0:
        r, g, b = (w - 510.0) / 70.0, 1.0, 0.0
    elif w < 645.0:
        r, g, b = 1.0, -(w - 645.0) / 65.0, 0.0
    else:
        r, g, b = 1.0, 0.0, 0.0

    # Roll off at the ends of vision, but never all the way to black.
    if w < 420.0:
        falloff = 0.3 + 0.7 * (w - 380.0) / 40.0
    elif w > 700.0:
        falloff = 0.3 + 0.7 * (780.0 - w) / 80.0
    else:
        falloff = 1.0
    return r * falloff, g * falloff, b * falloff


class AssetPack:
    """Base class for a look-and-sound pack.

    A subclass answers two questions: how a semantic thing is drawn, and what
    plays in a given musical context.

    Parameters
    ----------
    name : str
        Pack identifier, used in save state so a game can warn when the pack it
        was played with is missing.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def resolve(self, kind: str, name: str = "", state: str = "idle", **hints) -> Appearance:
        """Map a semantic thing to an appearance.

        Parameters
        ----------
        kind : str
            Broad category — ``"dye"``, ``"tile"``, ``"villager"``, ``"ui"``.
        name : str, optional
            Specific identity within the kind.
        state : str, optional
            Variant, e.g. ``"idle"``, ``"hurt"``, ``"selected"``.
        **hints
            Extra facts the game knows that a pack may use — notably
            ``emission_nm`` for a fluorophore.

        Returns
        -------
        Appearance
            How to draw it.
        """
        raise NotImplementedError

    def music_track(self, context: str) -> dict | None:
        """Return the track for a musical context.

        Parameters
        ----------
        context : str
            One of ``"overworld"``, ``"town"``, ``"battle"``, ``"underworld"``,
            ``"victory"``.

        Returns
        -------
        dict or None
            A track definition for :mod:`chisurf.gui.chigame.audio`, or ``None``
            for silence.
        """
        return None


class ProceduralPack(AssetPack):
    """The default pack: signed-distance shapes, no image or audio files.

    Parameters
    ----------
    name : str, optional
        Pack identifier.
    """

    #: Base palette, in sRGB. Anything not derived from data comes from here.
    PALETTE: dict[str, tuple[float, float, float, float]] = {
        "ink": (0.07, 0.08, 0.11, 1.0),
        "paper": (0.93, 0.94, 0.96, 1.0),
        "grass": (0.30, 0.55, 0.32, 1.0),
        "stone": (0.55, 0.56, 0.60, 1.0),
        "water": (0.22, 0.45, 0.70, 1.0),
        "path": (0.72, 0.66, 0.52, 1.0),
        "wall": (0.36, 0.31, 0.29, 1.0),
        "fog": (0.14, 0.15, 0.19, 1.0),
        "accent": (0.95, 0.72, 0.25, 1.0),
        "danger": (0.85, 0.28, 0.28, 1.0),
        "ui": (0.88, 0.90, 0.94, 1.0),
    }

    def __init__(self, name: str = "procedural") -> None:
        super().__init__(name)

    def resolve(self, kind: str, name: str = "", state: str = "idle", **hints) -> Appearance:
        """Resolve a semantic thing to a signed-distance appearance.

        Parameters
        ----------
        kind : str
            Broad category.
        name : str, optional
            Specific identity.
        state : str, optional
            Variant.
        **hints
            ``emission_nm`` colours a fluorophore from its real emission
            maximum; ``color`` overrides the palette outright.

        Returns
        -------
        Appearance
            How to draw it.
        """
        color = hints.get("color")
        if kind == "dye":
            nm = hints.get("emission_nm")
            rgb = wavelength_to_srgb(nm) if nm else (0.8, 0.8, 0.8)
            alpha = 0.55 if state == "faded" else 1.0
            return Appearance(shape=GLOW, color=(*rgb, alpha), param=0.6, softness=0.5, scale=1.4)
        if kind == "villager":
            return Appearance(
                shape=ROUND,
                color=color or self.PALETTE["paper"],
                param=0.45,
                scale=0.8,
            )
        if kind == "tile":
            return Appearance(shape=RECT, color=color or self.PALETTE.get(name, self.PALETTE["grass"]), softness=0.0)
        if kind == "wall":
            return Appearance(shape=ROUND, color=color or self.PALETTE["wall"], param=0.15)
        if kind == "fog":
            return Appearance(shape=RECT, color=color or self.PALETTE["fog"], softness=0.0)
        if kind == "hero":
            return Appearance(shape=ELLIPSE, color=color or self.PALETTE["accent"], scale=0.9)
        if kind == "cursor":
            return Appearance(shape=TRI, color=color or self.PALETTE["accent"])
        if kind == "aura":
            return Appearance(shape=RING, color=color or self.PALETTE["accent"], param=0.7, softness=0.15)
        if kind == "ui":
            variants = {
                "panel": Appearance(shape=ROUND, color=(0.10, 0.11, 0.15, 0.92), param=0.25),
                "bar": Appearance(shape=ROUND, color=self.PALETTE["accent"], param=0.5),
                "selected": Appearance(shape=ROUND, color=self.PALETTE["accent"], param=0.35),
                "spark": Appearance(shape=ELLIPSE, color=self.PALETTE["accent"], softness=0.4),
            }
            look = variants.get(name, Appearance(shape=RECT, color=self.PALETTE["ui"]))
            # An explicit colour must win here too. Dropping it silently turned
            # every pong paddle and spark white while the game looked correct.
            if color is not None:
                look = dataclasses.replace(look, color=color)
            return look
        return Appearance(shape=RECT, color=color or self.PALETTE["ui"])

    def music_track(self, context: str) -> dict | None:
        """Return a synthesised track for a musical context.

        Tracks are note data, not audio files — see
        :mod:`chisurf.gui.chigame.audio` for the format.

        Parameters
        ----------
        context : str
            The musical context.

        Returns
        -------
        dict or None
            Track definition, or ``None`` for silence.
        """
        return TRACKS.get(context)


#: Note data for the default pack. Scale degrees are semitone offsets from the
#: root; the sequencer turns them into samples. Kept small and diatonic so the
#: result is pleasant rather than merely present.
TRACKS: dict[str, dict] = {
    "overworld": {
        "root": 261.63,
        "tempo": 108,
        "wave": "triangle",
        "loop": True,
        "melody": [0, 4, 7, 12, 7, 4, 2, 4, 5, 4, 2, 0, -3, 0, 4, 7],
        "bass": [-12, -12, -5, -5, -8, -8, -12, -12],
    },
    "town": {
        "root": 293.66,
        "tempo": 92,
        "wave": "sine",
        "loop": True,
        "melody": [0, 2, 4, 5, 7, 5, 4, 2, 0, 2, 4, 2, 0, -3, -5, -3],
        "bass": [-12, -12, -7, -7, -10, -10, -12, -12],
    },
    "battle": {
        "root": 220.00,
        "tempo": 152,
        "wave": "square",
        "loop": True,
        "melody": [0, 0, 3, 0, 5, 3, 0, -2, 0, 0, 3, 5, 7, 5, 3, 0],
        "bass": [-12, -12, -12, -9, -12, -12, -12, -7],
    },
    "underworld": {
        "root": 174.61,
        "tempo": 76,
        "wave": "saw",
        "loop": True,
        "melody": [0, 1, 0, -2, 0, 3, 1, 0, -1, 0, 1, 3, 1, 0, -2, -4],
        "bass": [-12, -13, -12, -13, -15, -13, -12, -12],
    },
    "victory": {
        "root": 329.63,
        "tempo": 132,
        "wave": "triangle",
        "loop": False,
        "melody": [0, 4, 7, 12, 12, 7, 12, 16],
        "bass": [-12, -12, -5, 0],
    },
}
