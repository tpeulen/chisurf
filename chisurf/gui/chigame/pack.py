"""The pixel-art asset pack — real sheets behind the semantic draw calls.

:class:`~chisurf.gui.chigame.assets.ProceduralPack` proved the seam with
signed-distance shapes; this is the pack that proves it with art. Every PNG in
``assets/pixel`` is CC0 work from the Ninja Adventure pack by pixel-boy (see
``assets/pixel/CREDITS.md``), packed at load time by
:class:`~chisurf.gui.chigame.atlas.TextureAtlas`.

The vocabulary a game speaks does not change: ``scene.draw("character",
"warden", state="4,0", at=(x, y))`` still names a *character* and a *state*,
never a file or a pixel rectangle. What changes is what the call resolves to —
a frame of a hand-drawn sheet instead of an SDF shape. Anything the pack has no
art for falls through to the procedural pack, so a game can mix hand-drawn
tiles with spectral photon effects in one frame.

State convention for sheet characters, matching the sheets' layout (four
direction columns by seven animation rows): ``"<row>,<column>"``. The engine's
:class:`~chisurf.gui.chigame.actors.SheetAnimation` produces it; see that
module for the row meanings.
"""

from __future__ import annotations

import json
import pathlib

from .assets import Appearance, ProceduralPack
from .atlas import TextureAtlas
from .render import SPRITE

#: Where the shipped pixel pack lives.
PACK_ROOT = pathlib.Path(__file__).parent / "assets" / "pixel"


class SheetPack(ProceduralPack):
    """A look-and-sound pack backed by a directory of pixel art.

    Falls back to the procedural look for every name it does not carry, so it
    is a safe drop-in wherever the default pack was used.

    Parameters
    ----------
    directory : str or pathlib.Path, optional
        The pack directory: PNGs plus a ``pack.json`` manifest. Defaults to the
        shipped CC0 pixel pack.
    """

    def __init__(self, directory: str | pathlib.Path | None = None) -> None:
        super().__init__(name="pixel")
        self._root = pathlib.Path(directory) if directory is not None else PACK_ROOT
        self._manifest = json.loads((self._root / "pack.json").read_text(encoding="utf-8"))
        self._sheets: dict[str, str] = {}
        for alias, sheet in self._manifest.get("characters", {}).items():
            self._sheets[alias] = sheet
        self._sprites: dict[str, str] = dict(self._manifest.get("sprites", {}))
        self._strips: dict[str, str] = dict(self._manifest.get("vitality_strips", {}))
        self._atlas: TextureAtlas | None = None
        self._device = None

    # -- texture -----------------------------------------------------------

    def texture(self, device):
        """The packed GPU texture for this pack, built on first use.

        Parameters
        ----------
        device : wgpu.GPUDevice
            Device to build on. One pack builds once; asking again with a
            different device raises, because two devices cannot share a
            texture.

        Returns
        -------
        wgpu.GPUTexture
            The atlas texture.
        """
        if self._atlas is None:
            self._device = device
            from .atlas import load_pixel_pack

            atlas = load_pixel_pack(self._root, device)
            for prefix, spec in self._manifest.get("grids", {}).items():
                atlas.slice_grid(
                    spec["sheet"],
                    spec["columns"],
                    spec.get("rows"),
                    prefix=prefix,
                )
            self._atlas = atlas
        elif device is not self._device:
            raise ValueError("a SheetPack is bound to the device it first built on")
        return self._atlas.texture

    @property
    def atlas(self) -> TextureAtlas:
        """The pack's atlas; :meth:`texture` must have built it first.

        Returns
        -------
        TextureAtlas
        """
        if self._atlas is None:
            raise RuntimeError("call texture(device) before reading .atlas")
        return self._atlas

    def sheet_frame(self, alias: str, row: int, column: int) -> tuple[float, float, float, float]:
        """The uv rectangle of one cell of a character sheet.

        Parameters
        ----------
        alias : str
            Character alias from the manifest (``"hero"``).
        row : int
            Animation row.
        column : int
            Direction column.

        Returns
        -------
        tuple of float
            ``(u0, v0, u1, v1)``.
        """
        sheet = self._sheets.get(alias, alias)
        return self.atlas.uv(f"{sheet}:{row},{column}")

    def cell_uv(self, prefix: str, row: int, column: int):
        """The uv rectangle of any sliced grid cell, by grid prefix.

        Parameters
        ----------
        prefix : str
            Grid name from the manifest (``"floor"``, ``"hero"``).
        row, column : int
            Cell coordinates.

        Returns
        -------
        tuple of float
            ``(u0, v0, u1, v1)``.
        """
        return self.atlas.uv(f"{prefix}:{row},{column}")

    # -- AssetPack ---------------------------------------------------------

    def resolve(
        self, kind: str, name: str = "", state: str = "idle", **hints
    ) -> Appearance:
        look = self._resolve_art(kind, name, state, **hints)
        if look is not None:
            return look
        return super().resolve(kind, name, state, **hints)

    def _resolve_art(
        self, kind: str, name: str, state: str, **hints
    ) -> Appearance | None:
        if kind == "character":
            if name not in self._sheets:
                return None
            row, column = _parse_cell(state)
            uv = self.sheet_frame(name, row, column)
            if hints.get("flip"):
                uv = (uv[2], uv[1], uv[0], uv[3])
            return Appearance(
                shape=SPRITE,
                uv=uv,
                scale=1.0,
                color=hints.get("tint", (1.0, 1.0, 1.0, 1.0)),
            )
        grid = self._manifest["grids"].get(name)
        if grid is not None:
            row, column = _parse_cell(state)
            return Appearance(shape=SPRITE, uv=self.cell_uv(name, row, column))
        target = self._sprites.get(name)
        if target is not None:
            return Appearance(shape=SPRITE, uv=self.atlas.uv(target))
        return None


def _parse_cell(state: str) -> tuple[int, int]:
    """Read a ``"row,column"`` state into cell coordinates.

    Parameters
    ----------
    state : str
        Sheet state, ``"<row>,<column>"``.

    Returns
    -------
    tuple of int
        ``(row, column)``; ``(0, 0)`` when the state is not a cell, so an
        unknown spelling degrades to the idle-facing-down frame rather than
        raising mid-draw.
    """
    try:
        row_text, column_text = state.split(",")
        return int(row_text), int(column_text)
    except ValueError:
        return 0, 0
