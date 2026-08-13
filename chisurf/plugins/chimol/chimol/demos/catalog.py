"""Which demos ship, where their scripts are, and how they find their files.

Split out of :mod:`chimol.app.demos` -- which owns the Qt script editor -- for
the same reason :mod:`chimol.renderer.gui_state` was split out of the painter:
this half is a table and three path lookups, and the menu bar is generated from
it *at import time*. Leaving it beside a ``QDialog`` subclass meant that
building the menu bar imported a window system, so a host with no toolkit had
no Demo menu -- and a demo is the fastest way to find out whether that host
works at all.
"""
from __future__ import annotations

import pathlib

__all__ = [
    "DEMOS",
    "DEMO_DIR",
    "demo_path",
    "read_demo",
    "resolve_structure",
]

#: Where the shipped scripts live.
#: The ``.pml`` scripts, which are this module's own directory now that it
#: lives beside them rather than in the Qt layer.
DEMO_DIR = pathlib.Path(__file__).resolve().parent

#: Search path for the structures a demo names, so the scripts can say
#: ``load 148l.pdb`` rather than carrying an absolute path that only works on one
#: machine. Tried in order.
_DATA_DIRS = (
    pathlib.Path(__file__).resolve().parents[5]
    / "test" / "data" / "atomic_coordinates" / "pdb_files",
    pathlib.Path(__file__).resolve().parents[5]
    / "test" / "data" / "atomic_coordinates" / "trajectory" / "hgbp1",
)

#: Demo order and one-line descriptions. The order is a tour: what the viewer
#: looks like, then how to drive it, then what it can do that PyMOL cannot.
DEMOS: tuple[tuple[str, str, str], ...] = (
    ("cartoon", "Cartoon and colour", "A structure, coloured N to C."),
    ("selections", "Selections", "The PyMOL selection grammar, in colour."),
    ("representations", "Every representation", "Including ChiMOL's own."),
    ("lighting", "Lighting presets", "simple, soft, flat, default in turn."),
    ("publication", "Publication figure", "Flat shading with silhouettes."),
    ("trajectory", "Trajectory + intra_fit", "Why fitting makes a movie readable."),
    ("measure", "Measuring", "Surface area, bonds, hydrogens."),
    ("emdb_map", "EMDB density map", "Fetch a map and contour it."),
    ("npc_integrative", "NPC (integrative, PDB-IHM)", "A model made of beads, not atoms."),
    ("biofilm", "Biofilm growth (simulated)", "Cells divide, stack and change state."),
)


def resolve_structure(name: str) -> str:
    """Find a structure a demo script names, or return the name unchanged.

    Scripts say ``load 148l.pdb`` so they read like something a person would
    type; this is what lets that work from any working directory.

    One demo's material does not exist until it is computed -- see
    :mod:`chimol.demos.data` -- and is generated here, on first use, so the
    script that wants it still just says ``load``.

    Parameters
    ----------
    name : str
        What the script asked for.

    Returns
    -------
    str
        A path that exists, or *name* unchanged.

    Raises
    ------
    chimol.demos.data.DemoDataUnavailable
        When the file is one ChiMOL generates and generating it failed. Raised
        rather than swallowed: the alternative is a path that is not there, which
        reads as a missing download.
    """
    from .data import generated_demo_path

    candidate = pathlib.Path(name)
    if candidate.is_absolute() and candidate.exists():
        return str(candidate)
    for directory in _DATA_DIRS:
        found = directory / candidate.name
        if found.exists():
            return str(found)
    generated = generated_demo_path(candidate.name)
    if generated is not None:
        return str(generated)
    return name


def demo_path(key: str) -> pathlib.Path:
    """Path of a shipped demo script.

    Parameters
    ----------
    key : str
        The demo's key, as it appears in :data:`DEMOS`.

    Returns
    -------
    pathlib.Path
    """
    return DEMO_DIR / f"{key}.pml"


def read_demo(key: str) -> str:
    """The text of a shipped demo, or an empty string when it is missing.

    Parameters
    ----------
    key : str

    Returns
    -------
    str
    """
    path = demo_path(key)
    try:
        return path.read_text()
    except OSError:
        return ""
