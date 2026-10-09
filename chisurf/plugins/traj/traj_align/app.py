"""emtk app for the Align-Trajectory tool: every frame superposed onto frame 0.

Drawn from ``align_trajectory.view.json`` by the shared trajectory-tool app; the
spec's ``traj_align_io`` section is the trajectory and topology rows and the
save button, as the Qt section draws them, followed by the atom selection and
the stride.
"""

from __future__ import annotations

import pathlib

from chisurf.plugins.traj.emtk_tool import (
    SaveAction,
    TrajToolApp,
    icon_label,
    topology_field,
    trajectory_field,
)

from .view_model import AlignTrajectoryViewModel

HERE = pathlib.Path(__file__).parent

SAVE = SaveAction(
    key="save",
    label=icon_label("💾", "Save aligned…"),
    tooltip="Superpose every frame onto the first frame and write a new DCD.",
    dialog_title="Save aligned trajectory",
    filters=[("DCD trajectory", ["*.dcd"])],
    run=lambda model, path: model.save_aligned(path),
    suggest=lambda model: pathlib.Path(model.trajectory_filename).stem + "_aligned.dcd",
    failure="Align failed",
)


class AlignTrajectoryApp(TrajToolApp):
    """The Align-Trajectory window."""

    def __init__(self, model: AlignTrajectoryViewModel | None = None) -> None:
        super().__init__(
            model or AlignTrajectoryViewModel(),
            HERE,
            "align_trajectory.view.json",
            "traj_align_io",
            "Align trajectory",
            [trajectory_field(), topology_field()],
            SAVE,
        )


def make_app(**kwargs) -> AlignTrajectoryApp:
    """Construct the standalone Align-Trajectory app."""
    from chisurf.emtk.i18n import install

    install()
    return AlignTrajectoryApp()


__all__ = ["AlignTrajectoryApp", "make_app"]
