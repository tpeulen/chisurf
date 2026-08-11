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
                look, color=(look.color[0], look.color[1], look.color[2],
                             look.color[3] * float(alpha)))
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

    def text(
        self,
        content: str,
        at: tuple[float, float],
        height: float = 4.0,
        color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        align: str = "left",
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

        Returns
        -------
        float
            Advance width in world units, or ``0.0`` when no font is loaded.
        """
        if self.font is None:
            return 0.0
        return draw_text(self.batch, self.font, content, at, height, color, align)
