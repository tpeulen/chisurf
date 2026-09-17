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

    Glyphs are stored **trimmed to their ink**, side by side, so the atlas is a
    strip of varying-width cells rather than a grid. That is what makes the
    face proportional: an ``i`` occupies one column of the atlas and an ``m``
    seven, and the advance is read from the art instead of from a table
    somebody has to keep in step with it.

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
        Atlas pixels per font pixel -- headroom, not quality.
    """

    def __init__(
        self, device, pixel_size: int = 48, family: str | None = None, scale: int = pixelfont.SCALE
    ) -> None:
        self._device = device
        self._metrics = pixelfont.metrics()
        self.cell_h = pixelfont.HEIGHT * scale
        grid = pixelfont.atlas(scale)
        self.height, self.width = grid.shape
        self._columns = self.width / scale
        self.texture = self._upload(grid)

    def _box(self, char: str) -> tuple[int, int, int]:
        """Atlas placement and advance for one character, in font pixels.

        Parameters
        ----------
        char : str
            A single character.

        Returns
        -------
        tuple of int
            ``(atlas x, ink width, advance)``.
        """
        return self._metrics.get(char, self._metrics.get("?", (0, 5, 6)))

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
            A single character. Anything outside :data:`CHARSET` becomes the
            missing-character box.

        Returns
        -------
        tuple of float
            ``(u0, v0, u1, v1)``.
        """
        x, ink, _ = self._box(char)
        return x / self._columns, 0.0, (x + ink) / self._columns, 1.0

    def box_of(self, char: str) -> float:
        """How wide one character is drawn, as a fraction of the line height.

        Parameters
        ----------
        char : str
            A single character.

        Returns
        -------
        float
            Multiply by the drawn height to get the quad width.
        """
        return self._box(char)[1] / pixelfont.HEIGHT

    def advance_of(self, char: str) -> float:
        """How far the pen moves after one character, over the line height.

        Parameters
        ----------
        char : str
            A single character.

        Returns
        -------
        float
            Multiply by the drawn height to get the step.
        """
        return self._box(char)[2] / pixelfont.HEIGHT

    def measure(self, text: str, height: float) -> float:
        """How wide a string will actually be.

        Asking rather than assuming is the difference between a panel that fits
        its contents and one a longer name walks out of -- and with a
        proportional face there is no per-character constant to assume.

        Parameters
        ----------
        text : str
            The string.
        height : float
            Line height in world units.

        Returns
        -------
        float
            Advance width in world units.
        """
        return height * sum(self.advance_of(char) for char in text)

    @property
    def aspect(self) -> float:
        """A representative glyph width over the line height.

        Kept for callers that lay out on a nominal character width. Anything
        that needs the real thing should use :meth:`measure`.

        Returns
        -------
        float
            The advance of a digit, which is what most readouts are made of.
        """
        return self.advance_of("0")

    @property
    def pitch(self) -> float:
        """Same as :attr:`aspect`, kept for callers that ask by that name.

        Returns
        -------
        float
            Nominal advance over line height.
        """
        return self.aspect


def draw_text(
    batch,
    atlas: FontAtlas,
    text: str,
    pos: tuple[float, float],
    height: float,
    color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
    align: str = "left",
    shadow: bool = True,
) -> float:
    """Queue a string as one quad per character, over its own drop shadow.

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
    shadow : bool, optional
        Draw the dark offset copy underneath. On by default because unreadable
        text over a bright tile is the failure this prevents.

    Returns
    -------
    float
        Total advance width in world units, so callers can lay out following
        text without measuring twice.
    """
    from .render import GLYPH

    total = atlas.measure(text, height)
    if align == "center":
        x = pos[0] - total * 0.5
    elif align == "right":
        x = pos[0] - total
    else:
        x = pos[0]

    # Console dialogue is drawn twice, one pixel down and right, in a dark
    # tone. It is why that text stays readable over any background, and it is
    # most of why it reads as of the period rather than merely low-resolution.
    offset = height * (pixelfont.SHADOW / pixelfont.HEIGHT)
    passes = (
        ((offset, offset, (0.0, 0.0, 0.0, color[3] * 0.55)), (0.0, 0.0, color))
        if shadow
        else ((0.0, 0.0, color),)
    )

    for dx, dy, tone in passes:
        pen = x
        for char in text:
            box = height * atlas.box_of(char)
            if char != " ":
                batch.add(
                    pos=(pen + box * 0.5 + dx, pos[1] + dy),
                    size=(box, height),
                    color=tone,
                    shape=GLYPH,
                    uv=atlas.uv_for(char),
                )
            pen += height * atlas.advance_of(char)
    return total
