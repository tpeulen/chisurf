"""View-model for the fit controller's controls.

The controls used to be a Qt Designer file whose widgets were called
``spinBox_2`` … ``spinBox_6`` and whose steps field was labelled ``Stps``: the
layout, the labels and the (absent) tooltips were only editable in a GUI
designer, and what each control *meant* lived in the reading of
``fit_controller.py``. They are now declared in ``fitting_controls.view.json``
and rendered by :class:`chisurf.gui.autoform.AutoForm`, so a label, an order or
a new control is a change to data rather than to generated XML.

The model holds the values and forwards every interaction to the controller,
which keeps the behaviour exactly where it was.
"""

from __future__ import annotations

import pathlib
import typing

from chisurf.core.fitting.optimization_settings import (  # noqa: F401 - re-exported
    CHAIN_FORMAT_LABELS,
    OptimizationSettingsModel,
)

_VIEW = pathlib.Path(__file__).with_name("fitting_controls.view.json")

class FittingControlsModel:
    """Values and actions of the fit controller, bound by AutoForm.

    Parameters
    ----------
    controller : chisurf.gui.widgets.fitting.fit_controller.FittingControllerWidget
        The controller the actions are forwarded to. Held weakly by attribute
        only -- the model outlives nothing.
    dataset_labels : sequence of (str, str), optional
        ``(display, full)`` name pairs of the datasets to offer.
    chain_format : str, optional
        Initially selected chain format.
    """

    def __init__(
        self,
        controller,
        dataset_labels: typing.Sequence[tuple[str, str]] = (),
        chain_format: str = "er4",
    ):
        self._controller = controller
        self._dataset_labels = list(dataset_labels)
        self.dataset_index = 0
        self.xmin = 0
        self.xmax = 0
        self.xmin2 = 0
        self.xmax2 = 0
        self.steps_k = 1.0
        self.n_runs = 10
        self.chain_format = str(chain_format)
        self.result_index = 1
        self.local_first = True
        #: Whether MCTS also searches how each candidate is fitted.
        self.search_fit_settings = False

    # -- AutoForm plumbing -------------------------------------------------

    def view_spec(self):
        """Return the parsed view specification of the controls.

        Returns
        -------
        chisurf.core.dataspec.ViewSpec
            The spec loaded from ``fitting_controls.view.json``.
        """
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW)

    def dataset_options(self):
        """Return the datasets to offer, as ``(index, label)`` pairs.

        Returns
        -------
        list of tuple
            One pair per dataset of the fit; the label is the shortened file
            name, and the full name reaches the user through the tooltip the
            controller sets on the combo.
        """
        return [(i, label) for i, (label, _full) in enumerate(self._dataset_labels)]

    def set_dataset_labels(self, labels: typing.Sequence[tuple[str, str]]) -> None:
        """Replace the dataset list offered by the combo.

        Parameters
        ----------
        labels : sequence of (str, str)
            ``(display, full)`` name pairs.
        """
        self._dataset_labels = list(labels)

    # -- actions -----------------------------------------------------------

    def _trigger(self, action: str) -> None:
        """Fire one of the controller's actions.

        The designer file routed every button through a ``QAction`` so that a
        menu, a shortcut and the button all did the same thing. Keeping that
        indirection means the buttons rendered from the spec are still the same
        vocabulary the controller connects to.

        Parameters
        ----------
        action : str
            Attribute name of the action on the controller.
        """
        target = getattr(self._controller, action, None)
        if target is not None:
            target.trigger()

    def select_dataset(self) -> None:
        """Open the dataset selector."""
        self._trigger("actionChange_dataset")

    def auto_range(self) -> None:
        """Determine the fit range from the data."""
        self._trigger("actionAutoFitRange")

    def sample(self) -> None:
        """Start sampling the posterior."""
        self._trigger("actionErrorEstimate")

    def fit(self) -> None:
        """Run the optimiser."""
        self._trigger("actionFit")

    def mcts(self) -> None:
        """Search the model structure with MCTS and apply the winner."""
        self._trigger("actionMCTS")

    def settings(self) -> None:
        """Open the sampling and fitting settings."""
        handler = getattr(self._controller, "show_optimization_settings", None)
        if callable(handler):
            handler()


def show_optimization_settings(parent=None) -> bool:
    """Open the sampling/optimiser settings as a modal dialog.

    Parameters
    ----------
    parent : QtWidgets.QWidget, optional
        Dialog parent.

    Returns
    -------
    bool
        Whether the settings were accepted and applied.
    """
    from qtpy import QtWidgets

    from chisurf.gui.autoform import AutoForm

    model = OptimizationSettingsModel()
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Sampling and fitting settings")
    dialog.setModal(True)

    layout = QtWidgets.QVBoxLayout(dialog)
    form = AutoForm(model, parent=dialog)
    # Choosing a different sampler changes which settings exist, so the form is
    # rebuilt rather than showing the previous sampler's knobs.
    model.set_rebuild_callback(form.rebuild)
    layout.addWidget(form)
    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
        parent=dialog,
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec_() != QtWidgets.QDialog.Accepted:
        return False
    written = model.apply()
    if not written:
        # The values are live for this session but will not survive it, and a
        # dialog that closes quietly is a dialog that lied (RF-784).
        try:
            from chisurf.gui import dialogs

            dialogs.warning(
                parent,
                "Settings not saved",
                "The sampling and fitting settings apply to this session, but "
                "could not be written to your settings file.",
            )
        except Exception:
            import chisurf as cs

            cs.logging.warning("optimisation settings could not be written")
    return written
