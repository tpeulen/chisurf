"""The native H2MM app as a Qt panel for the burst-analysis workflow (step 7).

The workflow shell drives its panels through a small set of methods (``_set_folder``, ``detector_page``,
``_refresh_detector_combos``, ``_run_analysis``, ``stop``, ``apply_workflow_context``); :func:`make_panel` returns an
emtk ``ControlHost`` that answers them for :class:`.native.H2mmNativeApp`, so the step shows the emtk app and not the
Qt tool. Like the Qt tool it starts the fit for the folder it was given when it is first shown (a fit of unchanged
inputs is kept; a fit the user stopped does not start itself again).
"""

from __future__ import annotations

import copy
from typing import Any


class _DetectorPage:
    """What the shell calls on ``H2mmTool.detector_page``: load a detector definition."""

    def __init__(self, app) -> None:
        self.app = app

    def load_data_into_tables(self, settings: dict) -> None:
        self.app.editor.model.data = copy.deepcopy(settings)
        self.app.model.set_setup(settings)

    def get_settings(self) -> dict:
        return copy.deepcopy(self.app.model.setup)


def make_panel(parent: Any = None):
    """A Qt widget hosting the native H2MM app, with the workflow methods of the Qt tool."""
    from emtk.qt_host import ControlHost
    from qtpy import QtCore

    from .native import H2mmNativeApp

    app = H2mmNativeApp()
    host = ControlHost(app, background=(30, 32, 38))
    if parent is not None:
        host.setParent(parent)
    host._app = app
    host.model = app.model
    host.detector_page = _DetectorPage(app)
    host._refresh_detector_combos = lambda: None
    host._set_folder = lambda path: app.files_dropped([str(path)])
    host.set_folder = host._set_folder
    host.apply_workflow_context = app.model.apply_workflow_context

    def run(force: bool = False) -> None:
        """Fit through the shell's task seam (``run_in_background``), so the workflow sees the step as busy.

        The shell's Next button arms an advance and waits for the step's task to finish; a ``SnapshotJob`` is
        invisible to it. The work is the model's own ``compute`` on a snapshot; the result is copied back the way
        ``SnapshotJob.poll`` does.
        """
        from chisurf.gui.task import run_in_background

        model = app.model
        problem = model.can_run()
        if problem or app.job.busy:
            model.status_text = problem or model.status_text
            return
        snapshot = copy.copy(model)
        snapshot.setup = copy.deepcopy(model.setup)

        def worker(task):
            def observer(_event):
                task.raise_if_cancelled()
                task.set_progress(50, snapshot.status_text)

            snapshot._observers = [observer]
            snapshot.compute(force=force)
            return snapshot

        def done(snap):
            for key, value in vars(snap).items():
                if key != "_observers":
                    setattr(model, key, value)
            model.notify("result")

        def failed(error):
            model.status_text = f"Error: {error}"

        run_in_background(
            host,
            "Fitting H2MM models ...",
            worker,
            maximum=100,
            title="H2MM",
            owner=host,
            on_result=done,
            on_error=failed,
        )

    host._run_analysis = run
    host.stop = app.stop
    host._fit_is_running = lambda: app.job.busy

    class _AutoRun(QtCore.QObject):
        """Start the fit for the folder the workflow set when the panel is first shown."""

        def eventFilter(self, obj, event):  # noqa: N802 (Qt name)
            if event.type() == QtCore.QEvent.Show and not getattr(host, "_auto_ran", False):
                host._auto_ran = True
                QtCore.QTimer.singleShot(0, lambda: app.model.data_folder and run())
            return False

    # The shell's Next button finds the step's primary action by this object name and clicks it.
    from qtpy import QtWidgets

    run_button = QtWidgets.QToolButton(host)
    run_button.setObjectName("toolAction_run")
    run_button.setText("Run H2MM")
    run_button.hide()
    run_button.clicked.connect(lambda *_: run())
    host._run_button = run_button

    host._auto_filter = _AutoRun(host)
    host.installEventFilter(host._auto_filter)
    return host
