"""The trajectory tools' input rows come from the Datasets workspace (no ``…`` dialog, no drop).

``drop`` is what a drop on a tool became: the picked workspace rows handed to the tool's receive
hook (:func:`chisurf.plugins.traj.emtk_tool.receive_paths`), which routes each file to the row its
filter fits. ``check_browse_row`` checks an input row has no ``…`` of its own.
"""

from __future__ import annotations


def drop(ui, *paths) -> bool:
    """Hand *paths* to the window as workspace rows; True as the host's answer always was."""
    from chisurf.plugins.traj.emtk_tool import receive_paths

    try:
        receive_paths(ui.app, {"paths": [str(p) for p in paths]})
    except ValueError:
        pass  # nothing taken: the status line says so
    ui.draw(2)
    return True


def check_browse_row(make_app, row, *_args, **_kwargs) -> None:
    """An input row has no ``…``: its file is picked in the workspace Input section."""
    from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

    ui = Ui(make_app())
    try:
        ui.draw(3)
        assert row in ui.app.item_rects, row
        assert f"{row}_browse" not in ui.app.item_rects, f"{row} still has a browse button"
        assert "workspace_input_rows" in ui.app.item_rects
        assert not hasattr(type(ui.app), "on_files_dropped") or not callable(
            getattr(ui.app, "on_files_dropped", None)
        )
    finally:
        ui.app.close()
