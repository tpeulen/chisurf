"""Read the baked glyph atlas.

The atlas is produced by ``build_tools/bake_chrome_atlas.py`` and committed
beside this module. Baking needs a font engine; reading needs a JSON file and a
PNG, which is the whole point -- text renders identically wherever the chrome
runs, and layout no longer depends on whether a toolkit is present to measure
it.

Loading is lazy and cached: the panel repaints every frame and the atlas is one
image.
"""
from __future__ import annotations

import json
import pathlib
from typing import Optional

__all__ = ["Atlas", "load_atlas", "ATLAS_DIR"]

#: Where the baked atlas lives.
ATLAS_DIR = pathlib.Path(__file__).resolve().parent / "atlas"

_CACHE: dict[str, "Atlas"] = {}


class Atlas:
    """A baked font: where each glyph sits, and how wide it is.

    Parameters
    ----------
    meta : dict
        The contents of ``chrome.json``.

    Attributes
    ----------
    scale : int
        Supersampling factor the atlas was baked at. Every texel measurement
        below is at that scale; :meth:`advance` divides it out so callers work
        in the logical pixels the layout uses.
    """

    def __init__(self, meta: dict) -> None:
        self._meta = meta
        self.scale = int(meta["scale"])
        self.pad = int(meta["pad"])
        self.cell = tuple(meta["cell"])
        self.size = tuple(meta["size"])
        self.solid = tuple(meta["solid"])
        self.ascent = int(meta["ascent"])
        self._glyphs = meta["glyphs"]
        self._advance = float(meta["advance"]) / self.scale

    @property
    def line_height(self) -> float:
        """Height of one line, in logical pixels."""
        return float(self._meta["line_height"]) / self.scale

    def advance(self, string: str = "") -> float:
        """Advance width of *string*, in logical pixels.

        Parameters
        ----------
        string : str
            The text to measure. Empty gives one character's advance.

        Returns
        -------
        float

        Notes
        -----
        Monospaced, so this is a multiplication rather than a sum over the
        glyph table. That is a property of the baked font, not an assumption
        about text: the baker asserts one advance across both faces, because a
        proportional font would make every ``char_w``-based layout in the panel
        wrong in a way no single number could express.
        """
        return self._advance * (len(string) if string else 1)

    def cell_of(self, char: str, bold: bool = False) -> Optional[tuple]:
        """Return ``(x, y, w, h)`` of *char*'s cell, in texels.

        Parameters
        ----------
        char : str
            A single character.
        bold : bool
            Which face to look in.

        Returns
        -------
        tuple or None
            ``None`` when the character was not baked -- the caller draws
            nothing rather than a wrong glyph. A guard test keeps the charset
            in step with what the panel actually draws, so this should not
            happen in shipped code.
        """
        table = self._glyphs["bold" if bold else "regular"]
        entry = table.get(char)
        if entry is None:
            return None
        return entry[0], entry[1], entry[2], entry[3]

    @property
    def image_path(self) -> pathlib.Path:
        """Path to the atlas PNG."""
        return ATLAS_DIR / "chrome.png"


def load_atlas(name: str = "chrome") -> Atlas:
    """Load a baked atlas by name, cached.

    Parameters
    ----------
    name : str
        Base name of the ``.json`` / ``.png`` pair.

    Returns
    -------
    Atlas

    Raises
    ------
    FileNotFoundError
        If the atlas has not been baked. Raised rather than falling back to a
        measured font: a silent fallback would work on the desktop and fail
        only where there is no font engine, which is the one place nobody is
        watching.
    """
    cached = _CACHE.get(name)
    if cached is not None:
        return cached
    path = ATLAS_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"no baked glyph atlas at {path}; run "
            "`python -m build_tools.bake_chrome_atlas`"
        )
    atlas = Atlas(json.loads(path.read_text(encoding="utf-8")))
    _CACHE[name] = atlas
    return atlas
