"""The texture atlas — how pixel art gets onto the GPU.

The engine's first draft drew everything as signed-distance shapes and shipped
no image files at all. That proved the renderer but not the look: real tilesets
and character sheets are what a top-down game is drawn with. This module packs
any set of PNGs into one RGBA texture at load time and hands out normalised
uv rectangles for the batcher's ``SPRITE`` shape.

The reference (``junk/NinjaAdventure``, a CC0 Godot project) keeps its art as
per-thing PNGs — one sheet per character, one per tileset — and lets the engine
slice. The same convention is used here: images are added whole or as grids,
and the atlas shelves them into a single texture so the frame stays one draw
call.
"""

from __future__ import annotations

import pathlib

import numpy as np

#: No atlas may grow past this on either axis. Everything the pixel pack needs
#: fits in a fraction of it; the cap exists so a pathological pack fails loudly
#: at build time rather than silently on a device limit.
MAX_ATLAS_SIZE = 2048


class Frame:
    """One packed rectangle.

    Attributes
    ----------
    name : str
        The name the rectangle was added under.
    x0, y0 : int
        Top-left corner in atlas pixels.
    width, height : int
        Size in pixels.
    atlas : TextureAtlas
        The owning atlas; used to turn pixels into uv.
    """

    __slots__ = ("name", "x0", "y0", "width", "height", "atlas", "derived")

    def __init__(
        self, name: str, x0: int, y0: int, width: int, height: int, atlas: "TextureAtlas"
    ) -> None:
        self.name = name
        self.x0 = x0
        self.y0 = y0
        self.width = width
        self.height = height
        self.atlas = atlas
        #: ``(base_name, column, row)`` when this frame is a slice of another;
        #: the build re-points slices after the packer moves their sheet.
        self.derived: tuple[str, int, int] | None = None

    @property
    def size(self) -> tuple[int, int]:
        """Pixel size of the frame.

        Returns
        -------
        tuple of int
            ``(width, height)``.
        """
        return self.width, self.height

    @property
    def uv(self) -> tuple[float, float, float, float]:
        """Normalised uv rectangle, top-left origin.

        Returns
        -------
        tuple of float
            ``(u0, v0, u1, v1)`` covering exactly the frame's pixels.
        """
        w, h = self.atlas.size
        return (
            self.x0 / w,
            self.y0 / h,
            (self.x0 + self.width) / w,
            (self.y0 + self.height) / h,
        )


class TextureAtlas:
    """Shelf-packs images into one GPU texture.

    Usage: :meth:`add_image` / :meth:`add_grid` as often as needed, then read
    :attr:`texture` once — the atlas builds on first access and adding to a
    built atlas raises, so a stale texture can never be half-filled.

    Parameters
    ----------
    device : wgpu.GPUDevice
        Device the texture is created on.
    """

    def __init__(self, device) -> None:
        self._device = device
        self._frames: dict[str, Frame] = {}
        self._pending: list[tuple[str, np.ndarray]] = []
        self._gpu_texture = None
        self._size: tuple[int, int] | None = None

    # -- building ----------------------------------------------------------

    def add_image(self, name: str, image) -> Frame:
        """Add one whole image.

        Parameters
        ----------
        name : str
            Name to look the image up under later.
        image : PIL.Image.Image or numpy.ndarray
            RGBA source. Anything PIL accepts is converted; alpha-less sources
            become opaque.

        Returns
        -------
        Frame
            The pending frame (valid once the atlas builds).

        Raises
        ------
        RuntimeError
            If the atlas has already built.
        ValueError
            If the name is already taken or the image is empty.
        """
        array = self._to_rgba(image)
        if self._gpu_texture is not None:
            raise RuntimeError("the atlas is already built; add before reading .texture")
        if name in self._frames:
            raise ValueError(f"duplicate atlas name {name!r}")
        if array.shape[1] == 0 or array.shape[0] == 0:
            raise ValueError(f"image {name!r} is empty")
        self._pending.append((name, array))
        frame = Frame(name, 0, 0, array.shape[1], array.shape[0], self)
        self._frames[name] = frame
        return frame

    def slice_grid(
        self,
        base: str,
        columns: int,
        rows: int | None = None,
        prefix: str | None = None,
    ) -> list[Frame]:
        """Slice an already-added image into named sub-frames.

        Sub-frames are rectangles inside the sheet's own packed area, so
        nothing is uploaded twice and the sheet stays byte-identical to the
        author's file. The reference's character sheets are four direction
        columns by seven animation rows of sixteen-pixel cells; tilesets are
        columns of terrain and rows of variant.

        Parameters
        ----------
        base : str
            Name the whole sheet was added under.
        columns : int
            Cells across the sheet.
        rows : int, optional
            Cells down. Omitted infers square cells, which every sheet in the
            pixel pack uses.
        prefix : str, optional
            Name prefix for the cells; defaults to ``base``. Cells become
            ``prefix:r,c`` by row and column.

        Returns
        -------
        list of Frame
            Row-major frames, ``columns * rows`` of them.

        Raises
        ------
        KeyError
            If ``base`` was never added.
        RuntimeError
            If the atlas has already built.
        ValueError
            If the sheet does not hold the whole grid, or a cell name is taken.
        """
        if self._gpu_texture is not None:
            raise RuntimeError("the atlas is already built; slice before reading .texture")
        sheet = self._frames[base]
        cell_w = sheet.width // columns
        if cell_w == 0:
            raise ValueError(f"grid {base!r}: {columns} columns do not fit {sheet.width}px")
        if rows is None:
            # Square cells wherever they fit; a strip shorter than its cell
            # width (the fx sheets: leaves 72x7) is one row of full-height
            # cells rather than zero rows.
            rows = max(1, sheet.height // cell_w)
        cell_h = sheet.height // rows
        if rows == 0 or cell_h == 0 or cell_h * rows > sheet.height or cell_w * columns > sheet.width:
            raise ValueError(
                f"grid {base!r}: {columns}x{rows} cells of {cell_w}x{cell_h}px do not "
                f"fit a {sheet.width}x{sheet.height}px sheet"
            )
        prefix = prefix if prefix is not None else base
        frames: list[Frame] = []
        for row in range(rows):
            for column in range(columns):
                name = f"{prefix}:{row},{column}"
                if name in self._frames:
                    raise ValueError(f"duplicate atlas name {name!r}")
                cell = Frame(
                    name,
                    sheet.x0 + column * cell_w,
                    sheet.y0 + row * cell_h,
                    cell_w,
                    cell_h,
                    self,
                )
                cell.derived = (base, column, row)
                self._frames[name] = cell
                frames.append(cell)
        return frames

    # -- reading -----------------------------------------------------------

    def __contains__(self, name: str) -> bool:
        return name in self._frames

    def frame(self, name: str) -> Frame:
        """Look up a frame by name.

        Parameters
        ----------
        name : str
            As passed to :meth:`add_image` or built by :meth:`add_grid`.

        Returns
        -------
        Frame
            The frame.

        Raises
        ------
        KeyError
            If the name was never added.
        """
        return self._frames[name]

    def uv(self, name: str) -> tuple[float, float, float, float]:
        """Convenience: the uv rectangle of a named frame.

        Parameters
        ----------
        name : str
            Frame name.

        Returns
        -------
        tuple of float
            ``(u0, v0, u1, v1)``.
        """
        return self._frames[name].uv

    @property
    def frames(self) -> dict[str, Frame]:
        """Every frame, by name.

        Returns
        -------
        dict of str, Frame
        """
        return self._frames

    @property
    def size(self) -> tuple[int, int]:
        """Atlas size in pixels; builds the atlas if needed.

        Returns
        -------
        tuple of int
            ``(width, height)``.
        """
        self._build()
        return self._size  # type: ignore[return-value]

    @property
    def texture(self):
        """The packed GPU texture; builds on first access.

        Returns
        -------
        wgpu.GPUTexture
            One ``rgba8unorm`` texture with every added image in it.
        """
        self._build()
        return self._gpu_texture

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _to_rgba(image) -> np.ndarray:
        """Normalise any image source to an RGBA uint8 array.

        Parameters
        ----------
        image : PIL.Image.Image or numpy.ndarray
            The source.

        Returns
        -------
        numpy.ndarray
            ``(height, width, 4)`` uint8.
        """
        if isinstance(image, np.ndarray):
            array = image
        else:
            from PIL import Image as _Image

            if image.mode != "RGBA":
                image = image.convert("RGBA")
            array = np.asarray(image)
        array = np.ascontiguousarray(array, dtype=np.uint8)
        if array.ndim == 2:
            array = np.stack([array] * 3 + [np.full_like(array, 255)], axis=-1)
        if array.shape[2] == 3:
            alpha = np.full(array.shape[:2] + (1,), 255, dtype=np.uint8)
            array = np.concatenate([array, alpha], axis=2)
        return array

    def _build(self) -> None:
        """Shelf-pack every pending image and upload it once."""
        import wgpu

        if self._gpu_texture is not None:
            return
        if not self._pending:
            # A texture-less atlas still needs a valid texture for the batch's
            # binding, so an empty atlas packs a single transparent pixel.
            self._pending.append(("", np.zeros((1, 1, 4), dtype=np.uint8)))

        entries = sorted(
            ((name, array) for name, array in self._pending if name),
            key=lambda item: (-item[1].shape[0], -item[1].shape[1]),
        )
        # Images are shelved with their extruded margins included, and each
        # frame's own rectangle sits inset by the pad — so a sample that
        # rounds past the edge reads the extrusion, never the neighbour.
        padded_entries = [(name, _pad_image(array)) for name, array in entries]
        total_area = sum(a.shape[0] * a.shape[1] for _, a in padded_entries)
        width = 1 << max(4, (int(total_area**0.5) - 1).bit_length())
        while True:
            layout = self._shelve(padded_entries, width)
            if layout is not None:
                break
            if width >= MAX_ATLAS_SIZE:
                raise RuntimeError("the pixel pack does not fit a 2048px atlas")
            width *= 2
        height, placed = layout
        canvas = np.zeros((height, width, 4), dtype=np.uint8)
        for name, (x, y, padded) in placed.items():
            original = dict(entries)[name]
            canvas[y : y + padded.shape[0], x : x + padded.shape[1]] = padded
            frame = self._frames[name]
            frame.x0, frame.y0 = x + 1, y + 1
            frame.width, frame.height = original.shape[1], original.shape[0]
        for frame in self._frames.values():
            if frame.derived is None:
                continue
            base_name, column, row = frame.derived
            sheet = self._frames[base_name]
            frame.x0 = sheet.x0 + column * frame.width
            frame.y0 = sheet.y0 + row * frame.height

        self._gpu_texture = self._device.create_texture(
            size=(width, height, 1),
            format=wgpu.TextureFormat.rgba8unorm,
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
        )
        self._device.queue.write_texture(
            {"texture": self._gpu_texture},
            canvas.tobytes(),
            {"bytes_per_row": width * 4, "rows_per_image": height},
            (width, height, 1),
        )
        self._size = (width, height)
        self._pending.clear()

    @staticmethod
    def _shelve(
        entries: list[tuple[str, np.ndarray]], width: int
    ) -> tuple[int, dict[str, tuple[int, int, np.ndarray]]] | None:
        """Pack entries onto shelves of a fixed width.

        Parameters
        ----------
        entries : list of (str, numpy.ndarray)
            Images to place, largest first.
        width : int
            Atlas width to try.

        Returns
        -------
        tuple or None
            ``(total_height, {name: (x, y, array)})``, or ``None`` when an
            image is wider than ``width``.
        """
        placed: dict[str, tuple[int, int, np.ndarray]] = {}
        shelf_y = 0
        shelf_h = 0
        cursor_x = 0
        for name, array in entries:
            h, w = array.shape[:2]
            if w > width:
                return None
            if cursor_x + w > width:
                shelf_y += shelf_h
                shelf_h = 0
                cursor_x = 0
            placed[name] = (cursor_x, shelf_y, array)
            cursor_x += w
            shelf_h = max(shelf_h, h)
        return shelf_y + shelf_h, placed


def _pad_image(array: np.ndarray, pad: int = 1) -> np.ndarray:
    """Extrude an image's edge pixels into a margin.

    Point sampling does not interpolate *within* a texel, but the uv the
    vertex shader interpolates across a quad lands between texels at any
    non-integer screen scale, and a sample rounded one texel past the
    sprite's edge reads the *neighbour* sprite's first column. Extruding the
    sprite's own edge into a one-pixel margin gives that stray sample
    somewhere harmless to land — the same fix the game's own string-art
    atlas (:mod:`.pixelart`) arrived at independently, with a drawn-out
    diagnosis recorded there.

    Parameters
    ----------
    array : numpy.ndarray
        ``(h, w, 4)`` uint8.
    pad : int, optional
        Margin on every side, in pixels.

    Returns
    -------
    numpy.ndarray
        ``(h + 2*pad, w + 2*pad, 4)`` with edges extruded.
    """
    if pad <= 0:
        return array
    top = np.repeat(array[:1], pad, axis=0)
    bottom = np.repeat(array[-1:], pad, axis=0)
    padded = np.concatenate([top, array, bottom], axis=0)
    left = np.repeat(padded[:, :1], pad, axis=1)
    right = np.repeat(padded[:, -1:], pad, axis=1)
    return np.concatenate([left, padded, right], axis=1)


def load_pixel_pack(directory: str | pathlib.Path, device) -> TextureAtlas:
    """Build the atlas for a directory of PNGs.

    Every ``*.png`` under the directory is added whole under its relative
    path stem (``characters/hero`` → ``"characters/hero"``). Grids are slices
    the :class:`~chisurf.gui.chigame.pack.SheetPack` asks for by name.

    Parameters
    ----------
    directory : str or pathlib.Path
        The pack directory.
    device : wgpu.GPUDevice
        Device to build the texture on.

    Returns
    -------
    TextureAtlas
        The loaded atlas.
    """
    from PIL import Image

    atlas = TextureAtlas(device)
    root = pathlib.Path(directory)
    for path in sorted(root.rglob("*.png")):
        atlas.add_image(str(path.relative_to(root).with_suffix("")), Image.open(path))
    return atlas
