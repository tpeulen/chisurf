"""emtk app for the Join-Trajectories tool: two trajectories appended in time or stacked by atoms.

Drawn from ``join_trajectories.view.json`` by the shared trajectory-tool app; the
spec's ``traj_join_io`` section is the two trajectory rows, the topology row and
the save button, as the Qt section draws them, followed by the join mode, the
reversal toggles and the block size.
"""

from __future__ import annotations

import pathlib

from chisurf.plugins.traj.emtk_tool import SaveAction, TrajToolApp, topology_field, trajectory_field

from .view_model import JoinTrajectoriesViewModel

HERE = pathlib.Path(__file__).parent

SAVE = SaveAction(
    key="save",
    label="💾 Save joined…",
    tooltip="Join the two trajectories and write the result as a new DCD trajectory.",
    dialog_title="Save trajectory",
    filters=[("DCD trajectory", ["*.dcd"])],
    run=lambda model, path: model.save_joined(path),
    missing=lambda model: (None if model.trajectory_filename_1 and model.trajectory_filename_2
                           else "Open two trajectories first."),
    suggest=lambda model: pathlib.Path(model.trajectory_filename_1).stem + "_joined.dcd",
    failure="Join failed",
    cancelled="Join cancelled",
)

PATHS = [
    trajectory_field(key="trajectory_1", label="Trajectory 1", attr="trajectory_filename_1",
                     setter="set_trajectory_1", dialog_title="Open trajectory 1",
                     tooltip="The first trajectory: its frames come first (time) or its atoms first (atoms)."),
    trajectory_field(key="trajectory_2", label="Trajectory 2", attr="trajectory_filename_2",
                     setter="set_trajectory_2", dialog_title="Open trajectory 2",
                     tooltip="The second trajectory: appended after the first (time) or beside it (atoms)."),
    topology_field(tooltip="The structure that names the atoms of both trajectories; a DCD stores coordinates only."),
]


class JoinTrajectoriesApp(TrajToolApp):
    """The Join-Trajectories window."""

    def __init__(self, model: JoinTrajectoriesViewModel | None = None) -> None:
        super().__init__(model or JoinTrajectoriesViewModel(), HERE, "join_trajectories.view.json",
                         "traj_join_io", "Join trajectories", PATHS, SAVE)


def make_app(**kwargs) -> JoinTrajectoriesApp:
    """Construct the standalone Join-Trajectories app."""
    from chisurf.emtk.i18n import install

    install()
    return JoinTrajectoriesApp()


__all__ = ["JoinTrajectoriesApp", "make_app"]
