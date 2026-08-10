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
    #
    # The red rolloff starts at 645 rather than 700 deliberately. Above 645 the
    # hue is pure red and stops changing, so without a brightness gradient every
    # wavelength from there to 780 renders *identically* -- which showed up as
    # two adjacent spectral bands that were supposed to differ looking the same.
    # Eye sensitivity really does fall away across that span, so dimming it is
    # both the fix and the more faithful answer. It starts at 620 rather than
    # 645 because two bands only ~40 nm apart still have to be told apart.
    if w < 420.0:
        falloff = 0.3 + 0.7 * (w - 380.0) / 40.0
    elif w > 620.0:
        falloff = 0.28 + 0.72 * (780.0 - w) / 160.0
    else:
        falloff = 1.0
    return r * falloff, g * falloff, b * falloff


#: The visible range the games span, in nanometres. Violet is high-energy and
#: red is low: anything the games rank by difficulty ranks the same way.
VISIBLE_MIN_NM = 405.0
VISIBLE_MAX_NM = 680.0


def spectral_band(fraction: float) -> float:
    """Wavelength at a position across the visible range.

    Used wherever a game needs a series of distinct colours. Taking them from
    the spectrum rather than from a palette means the ordering carries meaning:
    the short-wavelength end is the energetic one, so "harder" and "bluer"
    coincide instead of being two unrelated facts the player must memorise.

    Parameters
    ----------
    fraction : float
        Position in 0..1. ``0`` is violet, ``1`` is deep red.

    Returns
    -------
    float
        Wavelength in nanometres.
    """
    f = min(max(float(fraction), 0.0), 1.0)
    return VISIBLE_MIN_NM + f * (VISIBLE_MAX_NM - VISIBLE_MIN_NM)


def photon_energy_rank(nanometres: float) -> float:
    """How energetic a wavelength is, normalised to 0..1.

    Photon energy goes as the reciprocal of wavelength, so this is not a linear
    ramp -- and using the real relation is what makes "violet is hardest" a
    consequence rather than a decoration.

    Parameters
    ----------
    nanometres : float
        Wavelength in nm.

    Returns
    -------
    float
        ``1`` at the violet end of the visible range, ``0`` at the red end.
    """
    inv = 1.0 / max(nanometres, 1e-6)
    lo = 1.0 / VISIBLE_MAX_NM
    hi = 1.0 / VISIBLE_MIN_NM
    return min(max((inv - lo) / (hi - lo), 0.0), 1.0)


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

    #: Base palette, in sRGB. The look is an optical bench in a darkened room,
    #: not an arcade cabinet: structure is desaturated graphite and steel, and
    #: **every saturated colour in the game is a wavelength**, produced by
    #: :func:`wavelength_to_srgb` rather than picked. Anything that glows is
    #: emitting; anything grey is hardware.
    PALETTE: dict[str, tuple[float, float, float, float]] = {
        # Room and enclosure.
        "ink": (0.030, 0.034, 0.042, 1.0),
        "fog": (0.075, 0.082, 0.098, 1.0),
        # Hardware: mounts, rails, housings.
        "steel": (0.42, 0.45, 0.50, 1.0),
        "graphite": (0.16, 0.18, 0.21, 1.0),
        "chrome": (0.68, 0.72, 0.78, 1.0),
        # Optics.
        "glass": (0.55, 0.72, 0.78, 1.0),
        "mirror": (0.80, 0.84, 0.88, 1.0),
        # Legible chrome text and rules.
        "ui": (0.78, 0.82, 0.88, 1.0),
        "dim": (0.44, 0.48, 0.55, 1.0),
        # Reserved semantics. "accent" is a readout colour, not decoration.
        "accent": (0.35, 0.85, 0.80, 1.0),
        "danger": (0.90, 0.32, 0.30, 1.0),
        # Terrain, kept muted so an emitting object always wins the eye.
        "grass": (0.16, 0.28, 0.24, 1.0),
        "stone": (0.30, 0.32, 0.35, 1.0),
        "water": (0.12, 0.26, 0.38, 1.0),
        "path": (0.34, 0.33, 0.30, 1.0),
        "wall": (0.20, 0.21, 0.24, 1.0),
        "paper": (0.86, 0.89, 0.93, 1.0),
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
        nm = hints.get("emission_nm")

        if kind == "photon":
            # A quantum of light: a small bright core inside a wide halo, in the
            # colour it actually is. Nothing else in the scene glows this hard.
            rgb = wavelength_to_srgb(nm) if nm else (0.90, 0.94, 1.0)
            if name == "halo":
                # A spill of light around something emitting, not the thing
                # itself: wide, faint, and never competing with its source.
                return Appearance(shape=GLOW, color=(*rgb, 0.30), param=0.9,
                                  softness=0.5, scale=3.4)
            return Appearance(shape=GLOW, color=(*rgb, 1.0), param=0.42, softness=0.5, scale=2.6)
        if kind == "band":
            # One emission band of a spectrum. Brightness follows photon energy,
            # so the violet end reads as the energetic one without a legend.
            rgb = wavelength_to_srgb(nm) if nm else (0.7, 0.7, 0.7)
            gain = 0.78 + 0.22 * photon_energy_rank(nm or 550.0)
            alpha = 0.45 if state == "depleted" else 1.0
            return Appearance(
                shape=ROUND,
                color=(rgb[0] * gain, rgb[1] * gain, rgb[2] * gain, alpha),
                param=0.30,
                softness=0.06,
            )
        if kind == "optic":
            # A mirror, dichroic or filter: hardware that redirects light. Tinted
            # by its own passband when one is given, otherwise plain glass.
            rgb = wavelength_to_srgb(nm) if nm else self.PALETTE["glass"][:3]
            return Appearance(
                shape=ROUND,
                color=(*[0.35 + 0.65 * c for c in rgb], 1.0),
                param=1.0,
                softness=0.10,
            )
        if kind == "detector":
            return Appearance(shape=ROUND, color=color or self.PALETTE["chrome"], param=0.35)
        if kind == "mount":
            return Appearance(shape=ROUND, color=color or self.PALETTE["graphite"], param=0.2)
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
