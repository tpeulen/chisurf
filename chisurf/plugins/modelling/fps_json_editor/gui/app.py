"""Structure › FRET › FPS JSON Editor: ChiMOL with its labelling editor open.

The fps.json editor is a plugin of ChiMOL (``chimol.plugins.labelling``: the *Labelling network* window with its
Positions, Distances, FlexFit and JSON tabs, the accessible volumes drawn in the viewer it sits in). ChiSurf ships
no editor of its own: this entry opens the ChiMOL window and runs ``fps_circle , , Positions`` once the viewer is
up. The headless half of this plugin (payload validation, PDB fetch, the CLI and RPC services) is ``core``, ``api``,
``cli`` and ``rpc``.
"""

from __future__ import annotations

#: The chimol command that opens the editor on its Positions tab.
OPEN_EDITOR = "fps_circle , , Positions"


def make_app():
    """The ChiMOL window with the labelling editor open."""
    from chisurf.plugins.chimol.app import make_app as make_chimol

    return make_chimol(commands=(OPEN_EDITOR,))


__all__ = ["OPEN_EDITOR", "make_app"]
