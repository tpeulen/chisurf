"""Structure › FRET › FPS JSON Editor: ChiMOL with its labelling editor open.

The fps.json editor is a plugin of ChiMOL (``chimol.plugins.labelling``: the *Labelling network* window with its
Positions, Distances, FlexFit and JSON tabs, the accessible volumes drawn in the viewer it sits in). ChiSurf ships
no editor of its own: this entry opens the ChiMOL window and runs ``fps_circle , , Positions`` once the viewer is
up. The headless half of this plugin (payload validation, PDB fetch, the CLI and RPC services) is ``core``, ``api``,
``cli`` and ``rpc``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chisurf.plugins.chimol.app import ChimolHostApp

#: The chimol command that opens the editor on its Positions tab.
OPEN_EDITOR = "fps_circle , , Positions"
#: The chimol tour the Guide button starts: the labelling editor's, not the viewer's general one.
GUIDE = "tour fps_editor"
#: The ``?`` page: the labelling plan, not the viewer's general help.
HELP = Path(__file__).parent / "help.md"


def make_app() -> ChimolHostApp:
    """The ChiMOL window with the labelling editor open."""
    from chisurf.plugins.chimol.app import make_app as make_chimol

    return make_chimol(commands=(OPEN_EDITOR,), guide_command=GUIDE, help_resource=HELP)


__all__ = ["GUIDE", "HELP", "OPEN_EDITOR", "make_app"]
