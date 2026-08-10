"""Text for chigame, without shipping a font.

Glyphs are rasterised into a coverage atlas with Qt at startup and uploaded as
one texture; the sprite batcher then draws each character as a ``GLYPH`` quad.
Qt is already a dependency and already knows about the platform's fonts and
hinting, so this buys real typography for no binary assets and no font parser.
"""

from __future__ import annotations

import numpy as np
import wgpu
from qtpy import QtCore, QtGui

#: Printable ASCII. Enough for scores, menus and villager dialogue.
CHARSET = "".join(chr(c) for c in range(32, 127))


class FontAtlas:
    """A monospace coverage atlas covering :data:`CHARSET`.

    Parameters
    ----------
    device : wgpu.GPUDevice
        Device the texture is created on.
    pixel_size : int, optional
        Rasterisation size. Glyphs are sampled with a linear filter, so this
        sets quality rather than on-screen size; drawing is scaled freely.
    family : str, optional
        Font family. A monospace family keeps the atlas a simple grid and makes
        layout arithmetic exact. Omitted asks the platform for its own fixed
        -pitch font, which is the only spelling guaranteed to resolve — the
        literal name "monospace" is not a family on macOS and costs a ~240 ms
        alias search before falling back to something proportional.
    """

    def __init__(self, device, pixel_size: int = 48, family: str | None = None) -> None:
        self._device = device
        if family is None:
            font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        else:
            font = QtGui.QFont(family)
        font.setStyleHint(QtGui.QFont.Monospace)
        font.setFixedPitch(True)
        font.setPixelSize(pixel_size)

        metrics = QtGui.QFontMetrics(font)
        self.cell_w = max(1, metrics.horizontalAdvance("M"))
        self.cell_h = max(1, metrics.height())
        self._ascent = metrics.ascent()

        image = QtGui.QImage(
            self.cell_w * len(CHARSET), self.cell_h, QtGui.QImage.Format_Grayscale8
        )
        image.fill(0)
        painter = QtGui.QPainter(image)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(255, 255, 255))
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        for index, char in enumerate(CHARSET):
            painter.drawText(
                QtCore.QPoint(index * self.cell_w, self._ascent), char
            )
        painter.end()

        self.width = image.width()
        self.height = image.height()
        self.texture = self._upload(image)

    def _upload(self, image: "QtGui.QImage"):
        """Copy a grayscale image into a single-channel texture.

        Parameters
        ----------
        image : QtGui.QImage
            Grayscale-8 atlas image.

        Returns
        -------
        wgpu.GPUTexture
            The uploaded texture.
        """
        # Qt pads each row to a 4-byte boundary, so the row stride is not
        # necessarily the width. Copying row by row into a tight array avoids a
        # sheared atlas, which is the classic symptom of trusting bytesPerLine.
        stride = image.bytesPerLine()
        raw = np.frombuffer(image.constBits().asstring(stride * image.height()), dtype=np.uint8)
        tight = raw.reshape(image.height(), stride)[:, : image.width()].copy()

        texture = self._device.create_texture(
            size=(image.width(), image.height(), 1),
            format=wgpu.TextureFormat.r8unorm,
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
        )
        self._device.queue.write_texture(
            {"texture": texture},
            tight.tobytes(),
            {"bytes_per_row": image.width(), "rows_per_image": image.height()},
            (image.width(), image.height(), 1),
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
        """Glyph cell width divided by its height.

        Returns
        -------
        float
            Used to lay out a string without stretching the glyphs.
        """
        return self.cell_w / self.cell_h


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

    advance = height * atlas.aspect
    total = advance * len(text)
    if align == "center":
        x = pos[0] - total * 0.5
    elif align == "right":
        x = pos[0] - total
    else:
        x = pos[0]

    for char in text:
        if char != " ":
            batch.add(
                pos=(x + advance * 0.5, pos[1]),
                size=(advance, height),
                color=color,
                shape=GLYPH,
                uv=atlas.uv_for(char),
            )
        x += advance
    return total
