"""emtk app for the trajectory converter: a frame range of a trajectory (or a folder of PDBs) rewritten.

Drawn from ``convert_structures.view.json`` by the shared trajectory-tool app:
the spec's Input panel (the topology, trajectory and target-folder rows of the
custom ``traj_convert_io`` section, the folder toggle, the frame range) and its
Output panel (name, format, split, the ``▶ Convert`` button of the custom
``traj_convert_run`` section), and the log.
"""

from __future__ import annotations

import pathlib

from chisurf.plugins.traj.emtk_tool import STRUCTURE_FILTERS, SaveAction, icon_label, TrajToolApp, topology_field, trajectory_field

from .view_model import MDConverterViewModel

HERE = pathlib.Path(__file__).parent


def _missing(model) -> str | None:
    if not model.trajectory:
        return "Choose a trajectory first."
    if not model.target_directory:
        return "Choose a target folder first."
    return None


CONVERT = SaveAction(
    key="convert",
    label=icon_label("▶", "Convert"),
    tooltip="Convert the trajectory with the current settings.",
    dialog_title=None,
    filters=[],
    run=lambda model, _target: model.convert(),
    missing=_missing,
    failure="Conversion failed",
    done="Conversion done!",
)

PATHS = [
    topology_field(attr="topology_path", filters=[("PDB-File", ["*.pdb"])], dialog_title="Open PDB-File",
                   tooltip="Topology (PDB) — required for trajectory formats without topology.",
                   browse_tooltip="Topology (PDB) — required for trajectory formats without topology."),
    trajectory_field(attr="trajectory", dialog_title="Open trajectory",
                     filters=[("Trajectory", ["*.dcd"])], folder=lambda model: model.use_folder,
                     placeholder="Drop a DCD trajectory (or, in folder mode, a folder of PDBs)",
                     tooltip="Input trajectory file, or a folder of PDBs when 'Input is a folder of PDBs' is on.",
                     browse_tooltip="Input trajectory file, or a folder of PDBs when 'Input is a folder of PDBs' "
                                    "is on."),
    trajectory_field(key="target", label="Target folder", attr="target_directory", setter="set_target_directory",
                     filters=STRUCTURE_FILTERS, folder=True, dialog_title="Choose Target-Folder",
                     placeholder="Folder the converted file(s) are written to",
                     tooltip="Output directory the converted file(s) are written to.",
                     browse_tooltip="Output directory the converted file(s) are written to."),
]


class MDConverterApp(TrajToolApp):
    """The trajectory converter window."""

    def __init__(self, model: MDConverterViewModel | None = None) -> None:
        super().__init__(model or MDConverterViewModel(), HERE, "convert_structures.view.json",
                         "traj_convert_io", "Trajectory-converter", PATHS, CONVERT, action_key="traj_convert_run")


def make_app(**kwargs) -> MDConverterApp:
    """Construct the standalone trajectory converter app."""
    from chisurf.emtk.i18n import install

    install()
    return MDConverterApp()


__all__ = ["MDConverterApp", "make_app"]
