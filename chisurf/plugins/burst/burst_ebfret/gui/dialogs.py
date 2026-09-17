"""ebFRET's dialogs, drawn with emtk.

One class per MATLAB dialog -- ``+ebfret/+ui/+dialog/*.m`` and the built-in
``questdlg``, ``inputdlg``, ``msgbox`` and ``uigetfile``/``uiputfile`` calls
of the main window -- with the same title, the same controls in the same order,
the same labels and the same defaults. A dialog is modal: the window draws it
over everything and routes the pointer only to it until it closes.

Each dialog's ``draw(gui)`` is an immediate-mode panel body; pressing *Ok*
calls the dialog's ``on_ok`` with exactly what the MATLAB function returns, and
*Cancel* calls ``on_cancel`` (when given) with what it returns on cancel.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Callable, Sequence
from typing import Any

from emtk import im
from emtk.file_dialog import FileDialog

__all__ = [
    "Dialog",
    "FileChooser",
    "Question",
    "MessageBox",
    "SpecDialog",
    "ClipOutliersForm",
    "RemoveBleachingForm",
    "SetPriorsForm",
    "SelectChannelsForm",
    "AssignSmdChannelsForm",
    "SelectAnalysisForm",
    "clip_outliers_dialog",
    "remove_bleaching_dialog",
    "set_priors_dialog",
    "select_channels_dialog",
    "assign_smd_channels_dialog",
    "select_analysis_dialog",
    "parse_number",
]

BUTTON_W = 90.0


def parse_number(text: str) -> float | None:
    """``str2num`` of an edit box: the number typed, or ``None``.

    Parameters
    ----------
    text : str
        Field contents.

    Returns
    -------
    float or None
    """
    try:
        return float(str(text).strip())
    except ValueError:
        return None


class Dialog:
    """A modal dialog: a title, a size and a body.

    Attributes
    ----------
    title : str
        Window title, as MATLAB's ``'name'``.
    size : tuple of float
        ``(width, height)`` in pixels.
    done : bool
        Set when the dialog has closed.
    """

    title = ""
    size = (320.0, 200.0)

    def __init__(self) -> None:
        self.done = False

    def close(self) -> None:
        """Mark the dialog closed."""
        self.done = True

    def draw(self, gui) -> None:  # pragma: no cover - overridden
        """Draw the body; ``gui`` offers ``edit``, ``dropdown`` and ``track``."""
        raise NotImplementedError


class FileChooser(Dialog):
    """``uigetfile`` / ``uiputfile``: an emtk :class:`~emtk.file_dialog.FileDialog`.

    Parameters
    ----------
    title : str
        Dialog title.
    mode : {"open", "save"}
        Choose files or name one.
    filters : sequence
        ``(label, patterns)`` pairs in the MATLAB filter order.
    on_ok : callable
        ``on_ok(paths, filter_index)`` with the 1-based filter index -- the
        third output MATLAB's dialogs return and ebFRET dispatches on.
    multiselect : bool
        ``'multiselect', 'on'``.
    directory : str, optional
        Start folder.
    """

    size = (620.0, 470.0)

    def __init__(
        self,
        title: str,
        mode: str,
        filters: Sequence,
        on_ok: Callable,
        multiselect: bool = False,
        directory: str | None = None,
    ) -> None:
        super().__init__()
        self.title = title
        self.on_ok = on_ok
        self.chooser = FileDialog(
            title, mode=mode, filters=filters, directory=directory, multiselect=multiselect, rows=13
        )

    def draw(self, gui) -> None:
        """Draw the file browser and hand over the choice."""
        result = self.chooser.draw()
        if result is False:
            gui.track("dialog.cancel")
            self.close()
        elif result:
            gui.track("dialog.ok")
            self.close()
            self.on_ok(list(result), self.chooser.filter_index + 1)


class Question(Dialog):
    """``questdlg``: a question and one button per answer.

    Parameters
    ----------
    title : str
        Dialog title.
    text : str
        The question.
    buttons : sequence of str
        Answers, in order.
    on_answer : callable
        ``on_answer(answer)``; closing without answering is not possible here.
    """

    def __init__(
        self, title: str, text: str, buttons: Sequence[str], on_answer: Callable[[str], None]
    ) -> None:
        super().__init__()
        self.title, self.text, self.buttons, self.on_answer = title, text, list(buttons), on_answer
        lines = max(2, text.count("\n") + 2)
        self.size = (max(380.0, 110.0 * len(self.buttons) + 40.0), 70.0 + 18.0 * lines)

    def draw(self, gui) -> None:
        """The question text and the answer buttons."""
        im.text_wrapped(self.text)
        im.spacing()
        for index, answer in enumerate(self.buttons):
            if index:
                im.same_line()
            if im.button(f"{answer}##answer{index}", (100.0, 0.0)):
                gui.track(f"dialog.{answer.lower()}")
                self.close()
                self.on_answer(answer)


class MessageBox(Dialog):
    """``msgbox`` / ``warndlg`` / ``errordlg``: text and an *OK* button.

    Parameters
    ----------
    title : str
        Dialog title.
    text : str
        The message.
    """

    def __init__(self, title: str, text: str) -> None:
        super().__init__()
        self.title, self.text = title, text
        lines = text.count("\n") + 1 + len(text) // 60
        self.size = (440.0, 80.0 + 18.0 * lines)

    def draw(self, gui) -> None:
        """The message and *OK*."""
        im.text_wrapped(self.text)
        im.spacing()
        if im.button("OK##message-ok", (BUTTON_W, 0.0)):
            gui.track("dialog.ok")
            self.close()


#: The folder the dialogs' view specs live in.
SPECS = pathlib.Path(__file__).resolve().parent


class SpecDialog(Dialog):
    """A dialog whose controls are declared in a ``view.json`` spec.

    The spec names every field, its label, its range and its description; the
    form model holds the values and the dialog's ``ok`` / ``cancel`` actions.
    :func:`emtk.view_form.draw_form` draws it.

    Parameters
    ----------
    spec : str
        File name of the spec beside this module.
    form : object
        The form model the spec's ``attr`` and ``action`` names refer to.
    """

    def __init__(self, spec: str, form: Any) -> None:
        super().__init__()
        from emtk.widgets.view_spec import load_view_spec
        from emtk.view_form import FormState

        self.spec = load_view_spec(SPECS / spec)
        self.form = form
        self.form.dialog = self
        self.state = FormState()

    def draw(self, gui) -> None:
        """Draw the declared form."""
        from emtk.view_form import draw_form

        self.state.on_used = lambda name: gui.track(f"dialog.{name}")
        draw_form(self.spec, self.form, self.state)


class _Form:
    """Base of a dialog's form model: ``ok`` / ``cancel`` close the dialog."""

    dialog: SpecDialog | None = None

    def _close(self) -> None:
        if self.dialog is not None:
            self.dialog.close()

    def cancel(self) -> None:
        """*Cancel*: close without doing anything."""
        self._close()


class ClipOutliersForm(_Form):
    """``inputdlg`` of ``clip_outliers.m``: *Select Range*.

    Parameters
    ----------
    on_ok : callable
        ``on_ok((clip_min, clip_max), max_outliers)``.
    """

    def __init__(self, on_ok: Callable) -> None:
        self.on_ok = on_ok
        self.clip_min, self.clip_max, self.max_outliers = -0.2, 1.2, 10

    def ok(self) -> None:
        """*OK*."""
        self._close()
        self.on_ok((float(self.clip_min), float(self.clip_max)), int(self.max_outliers))


class RemoveBleachingForm(_Form):
    """``+dialog/remove_bleaching.m``.

    Parameters
    ----------
    on_ok : callable
        ``on_ok(method, params)``: method 1 Manual / 2 Auto; params ``don``,
        ``acc``, ``sum``, ``fret``, ``pad`` with ``None`` for an unticked box.
    """

    KEYS = ("don", "acc", "sum", "fret", "pad")

    def __init__(self, on_ok: Callable) -> None:
        self.on_ok = on_ok
        self.method = "Manual"
        for key in self.KEYS:
            setattr(self, key, False)
            setattr(self, f"{key}_value", 0.0)

    def enabled(self, name: str) -> bool:
        """Checkboxes only in Manual; an edit only while its checkbox is ticked."""
        manual = self.method == "Manual"
        if name in self.KEYS:
            return manual
        if name.endswith("_value"):
            return manual and bool(getattr(self, name[:-len("_value")], False))
        return True

    def ok(self) -> None:
        """*Ok*."""
        self._close()
        params = {key: (float(getattr(self, f"{key}_value")) if getattr(self, key) else None)
                  for key in self.KEYS}
        self.on_ok(1 if self.method == "Manual" else 2, params)


class SetPriorsForm(_Form):
    """``+dialog/init_priors.m``: *Set Priors*.

    Parameters
    ----------
    on_ok : callable
        ``on_ok(theta, counts, status)`` -- ``theta`` ``mu_min, mu_max, sigma,
        tau``; ``counts`` ``mu, sigma, tau``; ``status`` 1 *All*, 2 *Current*.
    """

    def __init__(self, on_ok: Callable) -> None:
        self.on_ok = on_ok
        self.scope = "All"
        self.mu_min, self.mu_max, self.sigma, self.tau = 0.0, 1.0, 0.05, 100.0
        self.count_mu, self.count_sigma, self.count_tau = 0.1, 10.0, 10.0

    def ok(self) -> None:
        """*Ok*."""
        self._close()
        theta = {"mu_min": self.mu_min, "mu_max": self.mu_max, "sigma": self.sigma,
                 "tau": self.tau}
        counts = {"mu": self.count_mu, "sigma": self.count_sigma, "tau": self.count_tau}
        self.on_ok(theta, counts, 1 if self.scope == "All" else 2)


class SelectChannelsForm(_Form):
    """``+dialog/select_channels.m``: *Channels*, all ticked.

    Parameters
    ----------
    on_ok : callable
        ``on_ok(channels)``.
    """

    KEYS = ("donor", "acceptor", "fret", "viterbi_state", "viterbi_mean")

    def __init__(self, on_ok: Callable) -> None:
        self.on_ok = on_ok
        for key in self.KEYS:
            setattr(self, key, True)

    def ok(self) -> None:
        """*Ok*."""
        self._close()
        self.on_ok({key: bool(getattr(self, key)) for key in self.KEYS})


class AssignSmdChannelsForm(_Form):
    """``+dialog/assign_smd_channels.m``: *Assign Channels*.

    Parameters
    ----------
    labels : sequence of str
        The SMD's column labels.
    on_ok : callable
        ``on_ok(channels)`` -- ``donor``, ``acceptor``, ``fret`` as 1-based
        columns, ``None`` for the ones the *Signal Type* does not use.
    on_cancel : callable, optional
        Called on *Cancel*.
    """

    def __init__(self, labels: Sequence[str], on_ok: Callable,
                 on_cancel: Callable | None = None) -> None:
        self.labels = [str(label) for label in labels] or ["(none)"]
        self.on_ok, self.on_cancel = on_ok, on_cancel
        self.signal_type = "Donor-Acceptor"
        self.donor = self.acceptor = self.fret = self.labels[0]

    def column_labels(self) -> list[str]:
        """The popups' entries."""
        return list(self.labels)

    def enabled(self, name: str) -> bool:
        """Donor/Acceptor for a two-channel signal, FRET for a FRET signal."""
        if name in ("donor", "acceptor"):
            return self.signal_type == "Donor-Acceptor"
        if name == "fret":
            return self.signal_type == "FRET"
        return True

    def ok(self) -> None:
        """*Ok*."""
        self._close()
        column = self.labels.index
        if self.signal_type == "Donor-Acceptor":
            self.on_ok({"donor": column(self.donor) + 1, "acceptor": column(self.acceptor) + 1,
                        "fret": None})
        else:
            self.on_ok({"donor": None, "acceptor": None, "fret": column(self.fret) + 1})

    def cancel(self) -> None:
        """*Cancel*."""
        self._close()
        if self.on_cancel is not None:
            self.on_cancel()


class SelectAnalysisForm(_Form):
    """``@MainWindow/select_analysis.m``: *Select*.

    Parameters
    ----------
    states : sequence of int
        ``min_states:max_states``.
    groups : sequence of str
        The loaded groups; ``all`` is offered first.
    on_ok : callable
        ``on_ok(states, group)``.
    """

    def __init__(self, states: Sequence[int], groups: Sequence[str], on_ok: Callable) -> None:
        self.state_values = [str(int(k)) for k in states] or ["2"]
        self.group_values = ["all"] + sorted(set(groups))
        self.on_ok = on_ok
        self.states = self.state_values[0]
        self.group = "all"

    def state_options(self) -> list[str]:
        """*Number of States* entries."""
        return list(self.state_values)

    def group_options(self) -> list[str]:
        """*Time Series Group* entries."""
        return list(self.group_values)

    def ok(self) -> None:
        """*Ok*."""
        self._close()
        self.on_ok(int(self.states), str(self.group))


def clip_outliers_dialog(on_ok: Callable) -> SpecDialog:
    """The *Select Range* dialog of *Clip Outliers*."""
    dialog = SpecDialog("clip_outliers.view.json", ClipOutliersForm(on_ok))
    dialog.title, dialog.size = "Select Range", (360.0, 130.0)
    return dialog


def remove_bleaching_dialog(on_ok: Callable) -> SpecDialog:
    """The *Remove Photo-bleaching* dialog."""
    dialog = SpecDialog("remove_bleaching.view.json", RemoveBleachingForm(on_ok))
    dialog.title, dialog.size = "Remove Photo-bleaching", (300.0, 185.0)
    return dialog


def set_priors_dialog(on_ok: Callable) -> SpecDialog:
    """The *Set Priors* dialog."""
    dialog = SpecDialog("set_priors.view.json", SetPriorsForm(on_ok))
    dialog.title, dialog.size = "Set Priors", (290.0, 290.0)
    return dialog


def select_channels_dialog(on_ok: Callable) -> SpecDialog:
    """The *Channels* dialog of *Export > Traces*."""
    dialog = SpecDialog("select_channels.view.json", SelectChannelsForm(on_ok))
    dialog.title, dialog.size = "Channels", (240.0, 160.0)
    return dialog


def assign_smd_channels_dialog(labels: Sequence[str], on_ok: Callable,
                               on_cancel: Callable | None = None) -> SpecDialog:
    """The *Assign Channels* dialog of an SMD load."""
    dialog = SpecDialog("assign_smd_channels.view.json",
                        AssignSmdChannelsForm(labels, on_ok, on_cancel))
    dialog.title, dialog.size = "Assign Channels", (340.0, 150.0)
    return dialog


def select_analysis_dialog(states: Sequence[int], groups: Sequence[str],
                           on_ok: Callable) -> SpecDialog:
    """The *Select* dialog of the Traces and SMD exports."""
    dialog = SpecDialog("select_analysis.view.json", SelectAnalysisForm(states, groups, on_ok))
    dialog.title, dialog.size = "Select", (240.0, 150.0)
    return dialog


def default_directory() -> str:
    """Where file dialogs start: the current folder, as ``uigetfile`` does."""
    return os.getcwd()
