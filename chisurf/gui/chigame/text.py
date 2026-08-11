"""Text for chigame: the in-tree bitmap face, uploaded as one texture.

Glyphs come from :mod:`.pixelfont` -- string art in this repository, not a font
file and not the platform's. The sprite batcher then draws each character as a
``GLYPH`` quad against that coverage atlas.

This used to rasterise through Qt, and the result was the worst-looking thing
in every screenshot for two reasons. The first was a plain bug:
``QFontDatabase.systemFont(FixedFont)`` resolves to a **proportional** face on
this platform, and ``setFixedPitch(True)`` afterwards does not change what was
already resolved -- so narrow letters were centred in cells the width of an
``M``. The second is that a system UI font in a 16-bit game reads as a terminal
in costume however carefully it is measured.

Three things fall out of the change beyond the look. Text no longer needs Qt at
all, so a headless render and a windowed one draw identical glyphs. Advance and
glyph box are now separate numbers rather than one conflated ``aspect`` -- the
letters sit on a six-pixel pitch and are five pixels wide, which is what makes
them read as words. And the atlas is sampled with a nearest filter, because a
pixel font through a linear filter is a blurred pixel font.
"""

from __future__ import annotations

import numpy as np
import wgpu

from . import pixelfont

#: Printable ASCII. Enough for scores, menus and villager dialogue.
CHARSET = pixelfont.CHARSET


class FontAtlas:
    """The bitmap face, as a coverage atlas covering :data:`CHARSET`.

    Parameters
    ----------
    device : wgpu.GPUDevice
        Device the texture is created on.
    pixel_size : int, optional
        Ignored, and kept so existing callers keep working: the face is a
        bitmap, so there is no rasterisation size to choose. Its on-screen size
        is decided per draw.
    family : str, optional
        Ignored, for the same reason. There is one face and it is in the tree.
    scale : int, optional
        Atlas pixels per font pixel. Headroom for drawing a glyph larger than
        its cell, not quality -- see :data:`.pixelfont.SCALE`.
    """

    def __init__(self, device, pixel_size: int = 48, family: str | None = None,
                 scale: int = pixelfont.SCALE) -> None:
        self._device = device
        self.cell_w = pixelfont.WIDTH * scale
        self.cell_h = pixelfont.HEIGHT * scale
        #: Pixels from one character's left edge to the next. Larger than
        #: :attr:`cell_w` by the inter-character gap, which is part of the face
        #: rather than a layout parameter.
        self.advance_w = pixelfont.ADVANCE * scale

        grid = pixelfont.atlas(scale)
        self.height, self.width = grid.shape
        self.texture = self._upload(grid)

    def _upload(self, grid: np.ndarray):
        """Copy a coverage array into a single-channel texture.

        Parameters
        ----------
        grid : numpy.ndarray
            ``(rows, cols)`` uint8 coverage.

        Returns
        -------
        wgpu.GPUTexture
            The uploaded texture.
        """
        tight = np.ascontiguousarray(grid, dtype=np.uint8)
        rows, cols = tight.shape
        texture = self._device.create_texture(
            size=(cols, rows, 1),
            format=wgpu.TextureFormat.r8unorm,
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
        )
        self._device.queue.write_texture(
            {"texture": texture},
            tight.tobytes(),
            {"bytes_per_row": cols, "rows_per_image": rows},
            (cols, rows, 1),
        )
        return texture

    def uv_for(self, char: str) -> tuple[float, float, float, float]:
        """Atlas rectangle for one character.

        Parameters
        ----------
        char : str
            A single character. Anything outside :data:`CHARSET` becomes a space.

        Returns
        -------
        tuple of float
            ``(u0, v0, u1, v1)``.
        """
        index = CHARSET.find(char)
        if index < 0:
            index = 0
        u0 = index * self.cell_w / self.width
        u1 = (index + 1) * self.cell_w / self.width
        return u0, 0.0, u1, 1.0

    @property
    def aspect(self) -> float:
        """Glyph box width divided by its height.

        Returns
        -------
        float
            The shape of one character, used to size its quad so the face is
            never stretched.
        """
        return self.cell_w / self.cell_h

    @property
    def pitch(self) -> float:
        """Character-to-character advance, divided by the cell height.

        Keeping this apart from :attr:`aspect` is the difference between text
        that reads as words and text that reads as ``s e t t l e d``: the
        advance includes the gap between letters and the box does not, and
        conflating them was most of why the old text looked spindly.

        Returns
        -------
        float
            Multiply by the drawn height to get the step per character.
        """
        return self.advance_w / self.cell_h


def draw_text(
    batch,
    atlas: FontAtlas,
    text: str,
    pos: tuple[float, float],
    height: float,
    color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
    align: str = "left",
) -> float:
    """Queue a string as one quad per character.

    Parameters
    ----------
    batch : chisurf.gui.chigame.render.SpriteBatch
        Batch to append to.
    atlas : FontAtlas
        The rasterised glyphs.
    text : str
        Text to draw.
    pos : tuple of float
        Anchor position in world units; the vertical component is the centre of
        the line.
    height : float
        Cell height in world units.
    color : tuple of float, optional
        sRGB RGBA.
    align : {'left', 'center', 'right'}, optional
        Horizontal alignment relative to ``pos``.

    Returns
    -------
    float
        Total advance width in world units, so callers can lay out following
        text without measuring twice.
    """
    from .render import GLYPH

    step = height * atlas.pitch
    box = height * atlas.aspect
    total = step * len(text)
    if align == "center":
        x = pos[0] - total * 0.5
    elif align == "right":
        x = pos[0] - total
    else:
        x = pos[0]

    for char in text:
        if char != " ":
            batch.add(
                pos=(x + box * 0.5, pos[1]),
                size=(box, height),
                color=color,
                shape=GLYPH,
                uv=atlas.uv_for(char),
            )
        x += step
    return total
