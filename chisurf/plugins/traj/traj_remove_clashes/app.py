"""emtk app for the Remove-Clashed-Frames tool: frames with a too-close atom pair dropped.

Drawn from ``remove_clashes.view.json`` by the shared trajectory-tool app; the
spec's ``traj_remove_clashes_io`` section is the trajectory and topology rows and
the save button, as the Qt section draws them, followed by the atom selection,
the stride and the minimum distance.
"""

from __future__ import annotations

import pathlib

from chisurf.plugins.traj.emtk_tool import SaveAction, TrajToolApp, topology_field, trajectory_field

from .view_model import RemoveClashesViewModel

HERE = pathlib.Path(__file__).parent

SAVE = SaveAction(
    key="save",
    label="💾 Save clash-free…",
    tooltip="Drop every frame that contains an atom-atom clash and write a new DCD trajectory.",
    dialog_title="Save clash-free trajectory",
    filters=[("DCD trajectory", ["*.dcd"])],
    run=lambda model, path: model.save_clash_free(path),
    suggest=lambda model: pathlib.Path(model.trajectory_filename).stem + "_clash_free.dcd",
)


class RemoveClashesApp(TrajToolApp):
    """The Remove-Clashed-Frames window."""

    def __init__(self, model: RemoveClashesViewModel | None = None) -> None:
        super().__init__(model or RemoveClashesViewModel(), HERE, "remove_clashes.view.json",
                         "traj_remove_clashes_io", "Remove clashed frames",
                         [trajectory_field(), topology_field()], SAVE)


def make_app(**kwargs) -> RemoveClashesApp:
    """Construct the standalone Remove-Clashed-Frames app."""
    from chisurf.emtk.i18n import install

    install()
    return RemoveClashesApp()


__all__ = ["RemoveClashesApp", "make_app"]
