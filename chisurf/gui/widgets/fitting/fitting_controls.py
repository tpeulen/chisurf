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

_VIEW = pathlib.Path(__file__).with_name("fitting_controls.view.json")

#: Chain storage formats offered in the sampling panel. Kept in step with
#: :data:`chisurf.core.fitting.fit.CHAIN_FORMATS`; the labels say what the
#: choice costs, since that is the whole reason it exists.
#: Help for the run settings that are not any one sampler's to describe.
_RUN_SETTING_HELP = {
    'steps': "Steps per walker or chain. The diagnostics report whether it was enough.",
    'n_runs': ("Independent runs. Their disagreement is the R-hat that says whether the "
               "chain converged, so more than one is the point."),
    'substeps': "Steps between progress reports, cancellation checks and partial saves.",
}

CHAIN_FORMAT_LABELS = {
    "er4": "Text (.er4)",
    "hdf5": "HDF5 (.h5)",
}


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
            dataset_labels: typing.Sequence[typing.Tuple[str, str]] = (),
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

    def set_dataset_labels(self, labels: typing.Sequence[typing.Tuple[str, str]]) -> None:
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

    def settings(self) -> None:
        """Open the sampling and fitting settings."""
        handler = getattr(self._controller, "show_optimization_settings", None)
        if callable(handler):
            handler()


class OptimizationSettingsModel:
    """AutoForm view-model for the sampling and optimiser settings.

    Nothing here is a list of fields written down by hand. The samplers
    advertise what they take (:func:`chisurf.core.fitting.sample.sampler_settings`,
    derived from their signatures and docstrings), the chain formats come from
    :data:`chisurf.core.fitting.fit.CHAIN_FORMATS`, and the optimiser section is
    built from the settings that exist. A sampler that grows a knob grows it
    here; one that renames a parameter cannot leave a dead control behind.

    The values are written to the *user* settings on accept: these are what a
    run is configured by, and a dialog that changed them for the session only
    would misreport what the next run does.
    """

    def __init__(self, settings: dict = None):
        import chisurf as cs

        source = settings if settings is not None else cs.core.settings.cs_settings
        self._sampling = dict(source.get('optimization', {}).get('sampling', {}))
        self._leastsq = dict(source.get('optimization', {}).get('leastsq', {}))
        self._rebuild: typing.Callable[[], None] | None = None

        # Each sampler's own knobs are kept under its name, so switching from
        # one to another and back does not lose what was set, and no sampler is
        # ever handed a setting that belongs to a different one.
        self._per_sampler = dict(self._sampling.pop('samplers', {}) or {})
        self.method = cs.core.fitting.sample.resolve_sampler(
            self._sampling.get('method', 'blocked')
        )
        self.chain_format = str(self._sampling.get('chain_format', 'er4'))
        self._apply_sampler_defaults()
        for key, value in self._sampling.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                setattr(self, f"sampling_{key}", value)
        for section in cs.core.fitting.sample.optimizer_settings():
            key = section['attr']
            value = self._leastsq.get(key)
            if value is None:
                value = False if section['type'] == 'toggle' else (
                    0.0 if section.get('kind') == 'float' else 0
                )
            setattr(self, f"leastsq_{key}", value)

    # -- what the samplers advertise --------------------------------------

    def _sampler_sections(self) -> list:
        """Return the view sections of the currently selected sampler."""
        import chisurf as cs

        return cs.core.fitting.sample.sampler_settings(self.method)

    def _apply_sampler_defaults(self) -> None:
        """Give every advertised setting a value: configured, or its default."""
        configured = dict(self._per_sampler.get(self.method, {}))
        for section in self._sampler_sections():
            attr = section['attr']
            if attr in configured:
                setattr(self, attr, configured[attr])
            elif attr in self._sampling:
                setattr(self, attr, self._sampling[attr])
            elif 'default' in section:
                setattr(self, attr, section['default'])
            elif not hasattr(self, attr):
                setattr(self, attr, 0)

    def _remember_sampler_settings(self) -> None:
        """Keep what is on screen under the sampler it belongs to."""
        values = {}
        for section in self._sampler_sections():
            attr = section['attr']
            if hasattr(self, attr):
                values[attr] = getattr(self, attr)
        self._per_sampler[self.method] = values

    def sampler_options(self):
        """Return the advertised samplers as ``(name, label)`` pairs."""
        import chisurf as cs

        return cs.core.fitting.sample.sampler_choices()

    def chain_format_options(self):
        """Return the chain formats as ``(name, label)`` pairs."""
        import chisurf as cs

        return [
            (name, CHAIN_FORMAT_LABELS.get(name, f"{name} ({suffix})"))
            for name, suffix in cs.core.fitting.fit.CHAIN_FORMATS.items()
        ]

    def sampler_changed(self) -> None:
        """Rebuild the form so the new sampler's settings are the ones shown."""
        for name in self._per_sampler:
            pass
        self._apply_sampler_defaults()
        if self._rebuild is not None:
            self._rebuild()

    def set_rebuild_callback(self, callback) -> None:
        """Let the host rebuild the form when the sampler changes.

        Parameters
        ----------
        callback : callable
            Called with no arguments.
        """
        self._rebuild = callback

    # -- AutoForm plumbing -------------------------------------------------

    def view_spec(self):
        """Build the settings view from what the samplers and settings offer.

        Returns
        -------
        chisurf.core.dataspec.ViewSpec
            A spec with one panel for the sampler and its own settings, and one
            for the optimiser settings that exist.
        """
        import chisurf as cs
        from chisurf.core.dataspec import load_view_spec

        sampler = {
            "type": "panel", "title": "Sampler", "collapsible": False, "n_col": 2,
            "sections": [
                {"type": "choice", "attr": "method", "label": "Sampler",
                 "options_source": "sampler_options", "call": "sampler_changed",
                 "description": cs.core.fitting.sample.SAMPLERS[self.method]["description"]},
                {"type": "choice", "attr": "chain_format", "label": "Chains",
                 "options_source": "chain_format_options",
                 "description": "How the chains are stored. Text reads anywhere; "
                                "HDF5 is a compressed table about four times "
                                "smaller. Both open in nDXplorer."},
            ] + self._sampler_sections(),
        }
        advertised = {section['attr'] for section in self._sampler_sections()}
        run = {
            "type": "panel", "title": "Run", "collapsible": False, "n_col": 2,
            "sections": [
                {"type": "value", "attr": f"sampling_{key}",
                 "kind": "int" if isinstance(value, int) and not isinstance(value, bool)
                         else "float",
                 "label": cs.core.fitting.sample.setting_label(key),
                 "decimals": 4,
                 "description": _RUN_SETTING_HELP.get(key, f"Sampling setting '{key}'.")}
                for key, value in sorted(self._sampling.items())
                if key not in advertised
                and key not in ('method', 'chain_format')
                and isinstance(value, (int, float)) and not isinstance(value, bool)
            ],
        }
        # The optimiser advertises its settings the way the samplers do, so a
        # tolerance that ships as 0 is still a float field, and a boolean is a
        # toggle instead of being carried through invisibly (RF-783).
        optimiser_sections = []
        for section in cs.core.fitting.sample.optimizer_settings():
            section = dict(section)
            section['attr'] = f"leastsq_{section['attr']}"
            optimiser_sections.append(section)
        optimiser = {
            "type": "panel", "title": "Optimiser", "collapsible": False, "n_col": 2,
            "sections": optimiser_sections,
        }
        return load_view_spec({"sections": [sampler, run, optimiser]})

    # -- what comes back out ----------------------------------------------

    def sampling_settings(self) -> dict:
        """Return the sampling settings as they now stand."""
        self._remember_sampler_settings()
        values = {'method': str(self.method), 'chain_format': str(self.chain_format)}
        for key in self._sampling:
            if hasattr(self, f"sampling_{key}"):
                values[key] = getattr(self, f"sampling_{key}")
        values['samplers'] = {
            name: dict(settings) for name, settings in self._per_sampler.items()
        }
        return values

    def leastsq_settings(self) -> dict:
        """Return the optimiser settings as they now stand."""
        import chisurf as cs

        keys = {section['attr'] for section in cs.core.fitting.sample.optimizer_settings()}
        keys |= set(self._leastsq)
        return {
            key: getattr(self, f"leastsq_{key}")
            for key in sorted(keys)
            if hasattr(self, f"leastsq_{key}")
        }

    def apply(self) -> bool:
        """Write the settings to the session and to the user settings file.

        Returns
        -------
        bool
            Whether the settings file was written. The session is updated
            either way, so a read-only settings folder costs persistence, not
            the run the user is about to start.
        """
        import chisurf as cs
        from chisurf.core.settings.settings_utils import set_optimization_settings

        sampling, leastsq = self.sampling_settings(), self.leastsq_settings()
        try:
            optimization = cs.core.settings.cs_settings.setdefault('optimization', {})
            optimization.setdefault('sampling', {}).update(sampling)
            optimization.setdefault('leastsq', {}).update(leastsq)
        except Exception:
            cs.logging.exception("could not apply the settings to this session")
            return False
        return bool(set_optimization_settings(sampling=sampling, leastsq=leastsq))


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
