"""The drawing surface a game actually talks to.

A :class:`Scene` is the pairing of a sprite batch with an asset pack. Games call
:meth:`Scene.draw` with *meaning* — a kind, a name, a state — and the pack
decides what that looks like. No game ever names a colour or a shape, which is
what makes the whole look swappable.
"""

from __future__ import annotations

import dataclasses

from .assets import AssetPack, ProceduralPack
from .render import Camera, SpriteBatch
from .text import FontAtlas, draw_text


class Scene:
    """A frame under construction.

    Parameters
    ----------
    batch : chisurf.gui.chigame.render.SpriteBatch
        Where quads accumulate.
    pack : chisurf.gui.chigame.assets.AssetPack, optional
        Look and sound. Defaults to the procedural pack.
    camera : chisurf.gui.chigame.render.Camera, optional
        View. Defaults to a 100-unit-high view at the origin.
    font : chisurf.gui.chigame.text.FontAtlas, optional
        Glyphs. Text draws are ignored when absent, so a game that never draws
        text costs nothing.
    """

    def __init__(
        self,
        batch: SpriteBatch,
        pack: AssetPack | None = None,
        camera: Camera | None = None,
        font: FontAtlas | None = None,
    ) -> None:
        self.batch = batch
        self.pack = pack if pack is not None else ProceduralPack()
        self.camera = camera if camera is not None else Camera()
        self.font = font

    def draw(
        self,
        kind: str,
        name: str = "",
        at: tuple[float, float] = (0.0, 0.0),
        size: tuple[float, float] = (1.0, 1.0),
        state: str = "idle",
        rotation: float = 0.0,
        **hints,
    ) -> None:
        """Draw a semantic thing.

        Parameters
        ----------
        kind : str
            Broad category — ``"tile"``, ``"dye"``, ``"villager"``, ``"ui"``.
        name : str, optional
            Specific identity within the kind.
        at : tuple of float, optional
            Centre in world units.
        size : tuple of float, optional
            Footprint in world units, before the pack's own scale.
        state : str, optional
            Variant.
        rotation : float, optional
            Rotation in radians.
        **hints
            Facts the pack may use, such as ``emission_nm`` or an explicit
            ``color`` override. ``alpha`` is handled here rather than by the
            pack: it scales whatever opacity the pack chose, so a caller can
            fade *any* semantic thing -- a particle dying, a UI panel coming in
            -- without knowing what colour the pack picked or teaching every
            branch of every pack about transparency.
        """
        look = self.pack.resolve(kind, name, state, **hints)
        alpha = hints.get("alpha")
        if alpha is not None:
            look = dataclasses.replace(
                look,
                color=(look.color[0], look.color[1], look.color[2], look.color[3] * float(alpha)),
            )
        self.batch.add(
            pos=at,
            size=(size[0] * look.scale, size[1] * look.scale),
            color=look.color,
            shape=look.shape,
            param=look.param,
            rotation=rotation,
            softness=look.softness,
            uv=look.uv,
        )

    #: The frame a console dialogue box is made of, outside in: a near-black
    #: outer edge, a bright inner rule, then the fill. Three flat bands and no
    #: gradient -- the look comes from the *rule*, which is what a single
    #: translucent rounded rectangle can never give you however carefully it is
    #: tinted.
    FRAME: tuple[tuple[float, float, float, float], ...] = (
        (0.043, 0.047, 0.078, 0.98),
        (0.62, 0.70, 0.90, 1.0),
        (0.086, 0.11, 0.26, 0.98),
    )

    #: Thickness of each band, in world units at a nominal 1.0 scale.
    FRAME_BANDS: tuple[float, float] = (2.0, 1.0)

    def window(
        self,
        at: tuple[float, float],
        size: tuple[float, float],
        scale: float = 1.0,
        fill: tuple[float, float, float, float] | None = None,
    ) -> None:
        """Draw a framed box in the console-dialogue style.

        A translucent rounded rectangle is what a modern UI does and it reads
        as a modern UI. The boxes these games used are **framed**: a dark outer
        edge, a bright rule one pixel inside it, and a flat saturated fill. The
        rule is the whole effect -- it is what makes the box sit *on* the
        picture instead of floating over it, and it costs two extra quads.

        Parameters
        ----------
        at : tuple of float
            Centre, in world units.
        size : tuple of float
            Outer size, in world units.
        scale : float, optional
            Multiplies the band thicknesses, so a box keeps its proportions
            when the view is zoomed.
        fill : tuple of float, optional
            Override for the innermost colour.
        """
        width, height = size
        edge, rule = (band * scale for band in self.FRAME_BANDS)
        bands = (
            (width, height, self.FRAME[0]),
            (width - edge * 2.0, height - edge * 2.0, self.FRAME[1]),
            (
                width - (edge + rule) * 2.0,
                height - (edge + rule) * 2.0,
                fill if fill is not None else self.FRAME[2],
            ),
        )
        for band_w, band_h, colour in bands:
            if band_w <= 0.0 or band_h <= 0.0:
                continue
            self.draw("ui", "frame", at=at, size=(band_w, band_h), color=colour)

    def text(
        self,
        content: str,
        at: tuple[float, float],
        height: float = 4.0,
        color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        align: str = "left",
        shadow: bool = True,
    ) -> float:
        """Draw a string.

        Parameters
        ----------
        content : str
            Text to draw.
        at : tuple of float
            Anchor in world units; vertically the centre of the line.
        height : float, optional
            Cell height in world units.
        color : tuple of float, optional
            sRGB RGBA.
        align : {'left', 'center', 'right'}, optional
            Alignment relative to ``at``.
        shadow : bool, optional
            Draw the dark offset copy underneath, as console dialogue does.

        Returns
        -------
        float
            Advance width in world units, or ``0.0`` when no font is loaded.
        """
        if self.font is None:
            return 0.0
        return draw_text(self.batch, self.font, content, at, height, color, align, shadow=shadow)
