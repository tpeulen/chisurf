"""emtk app for the Save-Topology tool: frame 0 of a trajectory written as a PDB.

Drawn from ``save_topology.view.json`` by the shared trajectory-tool app; the
spec's ``traj_save_topology_io`` section is the trajectory and topology rows
and the save button, as the Qt section draws them.
"""

from __future__ import annotations

import pathlib

from chisurf.plugins.traj.emtk_tool import SaveAction, TrajToolApp, icon_label, topology_field, trajectory_field

from .view_model import SaveTopologyViewModel

HERE = pathlib.Path(__file__).parent


def _suggest(model) -> str:
    return pathlib.Path(model.trajectory_filename).stem + "_frame0.pdb"


SAVE = SaveAction(
    key="save",
    label=icon_label("💾", "Save topology…"),
    tooltip="Write the first frame of the trajectory as a PDB file.",
    dialog_title="Save PDB-file",
    filters=[("PDB-files", ["*.pdb"])],
    run=lambda model, path: model.save_topology(path),
    suggest=_suggest,
)


class SaveTopologyApp(TrajToolApp):
    """The Save-Topology window."""

    def __init__(self, model: SaveTopologyViewModel | None = None) -> None:
        super().__init__(model or SaveTopologyViewModel(), HERE, "save_topology.view.json",
                         "traj_save_topology_io", "Save topology",
                         [trajectory_field(), topology_field()], SAVE)


def make_app(**kwargs) -> SaveTopologyApp:
    """Construct the standalone Save-Topology app."""
    from chisurf.emtk.i18n import install

    install()
    return SaveTopologyApp()


__all__ = ["SaveTopologyApp", "make_app"]
