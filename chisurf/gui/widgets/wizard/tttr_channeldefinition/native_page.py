"""The retained wizard page hosts the existing native detector editor and portable model."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
from emtk.i18n import tr
from emtk.qt_host import ControlHost
from qtpy import QtCore, QtWidgets

from chisurf.core.setup_channel_definition import ChannelDefinition
from chisurf.emtk.channel_definition import BINNINGS
from chisurf.gui.qt_lifetime import is_deleted
from chisurf.plugins.core.setup_channel_definition.gui.app import SetupChannelDefinitionApp
from chisurf.plugins.core.setup_channel_definition.gui.model import default_settings


class DetectorWizardPage(QtWidgets.QWizardPage):
    """One native surface in the existing Qt wizard/navigation shell."""

    detectorsChanged = QtCore.Signal()
    micro_time_binningChanged = QtCore.Signal(int)

    def __init__(self, json_file=None, *args, model=None, settings=None, setups_file=None,
                 show_edit_json=False, show_save=False, show_setups_file=True,
                 show_setup_selection=True, show_help=True, show_tttr_reading=True,
                 show_tables=True, show_add_inputs=True, allow_finish=True, **kwargs):
        """Load a working definition or injected model without conflating its named setup store."""
        super().__init__(*args, **kwargs)
        self.setTitle(tr("Detectors and PIE-window definition"))
        self._closed = False
        self._owners = []
        self._lifecycle_owner = self.parent()
        self._allow_finish = bool(allow_finish)
        injected_model = model is not None
        self._previous_callback = model.on_changed if model is not None else None
        if model is None:
            data = copy.deepcopy(settings) if settings is not None else default_settings()
            if json_file:
                data = json.loads(Path(json_file).read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("Detector definition must be a JSON object.")
                if "setups" in data:
                    library = data.get("setups") or {}
                    name = data.get("last_used")
                    name = name if name in library else next(iter(library), "")
                    data = copy.deepcopy(library.get(name, {}))
                    data["setup_name"] = name
                    setups_file = setups_file or str(json_file)
            model = ChannelDefinition(data, file_path=setups_file)
        elif setups_file is not None:
            model.file_path = str(setups_file)
        self.model = model
        self._last_settings = model.get_settings()
        visibility = {"edit_json": bool(show_edit_json), "save_definition": bool(show_save),
                      "setups_file": bool(show_setups_file), "setup_selection": bool(show_setup_selection),
                      "help": bool(show_help), "tttr_reading": bool(show_tttr_reading),
                      "tables": bool(show_tables), "add_inputs": bool(show_add_inputs)}
        self.app = SetupChannelDefinitionApp(model=model, on_changed=self._changed,
                    open_last_used=not injected_model and json_file is None and settings is None,
                    visibility=visibility, on_definition_saved=self._definition_saved)
        self.editor = self.app.page
        self._owned_callback = self.model.on_changed
        self.host = ControlHost(self.app, parent=self)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.host.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.host)
        self._watch_owners()

    def sizeHint(self):
        """Offer the existing detector editor a usable page without fixing its window size."""
        return QtCore.QSize(800, 700)

    def minimumSizeHint(self):
        """Leave compact hosts scrollable while preventing an eighty-pixel collapsed page."""
        return QtCore.QSize(320, 240)

    def event(self, event):
        """Keep the existing standalone-page focus behavior outside a QWizard."""
        if self.wizard() is None:
            result = QtWidgets.QWidget.event(self, event)
        else:
            result = super().event(event)
        if event.type() == QtCore.QEvent.ParentChange and hasattr(self, "host"):
            self._watch_owners()
        return result

    def _watch_owners(self):
        """Observe actual Qt owner lifetime, including later QWizard reparenting."""
        for owner in self._owners:
            if not is_deleted(owner):
                owner.removeEventFilter(self)
                owner.destroyed.disconnect(self._owner_finished)
                if isinstance(owner, QtWidgets.QDialog):
                    owner.finished.disconnect(self._owner_finished)
        self._owners = []
        owner = self.parent()
        while owner is not None:
            owner.installEventFilter(self)
            owner.destroyed.connect(self._owner_finished)
            if isinstance(owner, QtWidgets.QDialog):
                owner.finished.connect(self._owner_finished)
            self._owners.append(owner)
            owner = owner.parent()
        owner = self._lifecycle_owner
        if owner is not None and not is_deleted(owner) and owner not in self._owners:
            owner.installEventFilter(self)
            owner.destroyed.connect(self._owner_finished)
            if isinstance(owner, QtWidgets.QDialog):
                owner.finished.connect(self._owner_finished)
            self._owners.append(owner)

    def eventFilter(self, owner, event):
        """Release native work after an enclosing owner accepts its close event."""
        if event.type() == QtCore.QEvent.Close and not self._closed:
            QtCore.QTimer.singleShot(0, lambda: self._close_hidden_owner(owner))
        elif event.type() == QtCore.QEvent.ParentChange and not self._closed:
            self._watch_owners()
        return False

    def _close_hidden_owner(self, owner):
        """A rejected close keeps the visible owner and native surface alive."""
        if not self._closed and owner in self._owners and (is_deleted(owner) or not owner.isVisible()):
            self._close_native()

    def _owner_finished(self, *args):
        """A real dialog completion or owner destruction also releases its native child."""
        self._close_native()

    def _changed(self, settings):
        """Relay actual definition changes once, with a separate binning signal."""
        previous = self._last_settings
        old_binning = previous["tttr_reading"].get("micro_time_binning", 1)
        new_binning = settings["tttr_reading"].get("micro_time_binning", 1)
        self._last_settings = copy.deepcopy(settings)
        if self._closed or is_deleted(self):
            return
        if callable(self._previous_callback):
            self._previous_callback(settings)
        if self._closed or is_deleted(self):
            return
        old_body = {k: v for k, v in previous.items() if k != "tttr_reading"}
        new_body = {k: v for k, v in settings.items() if k != "tttr_reading"}
        if old_body != new_body:
            self.detectorsChanged.emit()
        if self._closed or is_deleted(self):
            return
        if old_binning != new_binning:
            self.micro_time_binningChanged.emit(int(new_binning))
        if self._closed or is_deleted(self):
            return
        self.app.request_frame()

    def _definition_saved(self, path):
        """Only a successful full-definition save enables the wizard's Finish button."""
        if not self._closed and not is_deleted(self) and not self._allow_finish:
            self._allow_finish = True
            self.completeChanged.emit()

    def isComplete(self):
        """Preserve the caller's initial finish policy until an actual successful save."""
        return self._allow_finish

    def get_settings(self):
        """Return the portable complete definition, including unknown scientific metadata."""
        return self.model.get_settings()

    def set_settings(self, settings):
        """Replace the working definition through the native owner's existing loader."""
        self.app.load_data_into_tables(settings)

    load_data_into_tables = set_settings

    def channels(self):
        """Return the derived PIE-window × detector routing map."""
        return self.get_settings()["channels"]

    @property
    def detectors(self):
        """The current named detector definitions."""
        return self.get_settings()["detectors"]

    @detectors.setter
    def detectors(self, value):
        data = self.get_settings()
        data["detectors"] = copy.deepcopy(value)
        self.set_settings(data)

    @property
    def windows(self):
        """The current named raw-channel PIE windows."""
        return self.get_settings()["windows"]

    @windows.setter
    def windows(self, value):
        data = self.get_settings()
        data["windows"] = copy.deepcopy(value)
        self.set_settings(data)

    def update_detector(self, name, values):
        """Update named scientific fields, retaining metadata and suppressing identical edits."""
        detector = self.model.data["detectors"][name]
        if all(key in detector and detector[key] == value for key, value in values.items()):
            return False
        detector.update(copy.deepcopy(values))
        self.model.changed()
        return True

    @property
    def tttr_reading(self):
        """Acquisition timing in ns/ps and the current integer microtime binning."""
        return self.get_settings()["tttr_reading"]

    @tttr_reading.setter
    def tttr_reading(self, value):
        current = self.model.data.setdefault("tttr_reading", {})
        changed = any(current.get(key) != v for key, v in value.items())
        if changed:
            current.update(copy.deepcopy(value))
            self.model.changed()

    @property
    def micro_time_binning(self):
        """The current microtime grouping factor."""
        return int(self.tttr_reading.get("micro_time_binning", 1))

    @micro_time_binning.setter
    def micro_time_binning(self, value):
        value = int(value)
        if value <= 0:
            raise ValueError("Microtime binning must be positive.")
        self.tttr_reading = {"micro_time_binning": value}

    @property
    def binning_options(self):
        """The native editor's declared binning choices."""
        return tuple(map(int, BINNINGS))

    @property
    def filetype(self):
        """Return None for automatic container detection, otherwise the declared format."""
        value = self.tttr_reading.get("file_type")
        return None if value is None or str(value).lower() == "auto" else value

    @filetype.setter
    def filetype(self, value):
        self.tttr_reading = {"file_type": value or "Auto"}

    @property
    def effective_micro_time_resolution(self):
        """Effective raw timing × binning in picoseconds."""
        return self.tttr_reading["effective_micro_time_resolution"]

    @property
    def excitation_period(self):
        """The excitation period in nanoseconds."""
        return self.tttr_reading["excitation_period"]

    @property
    def current_setup_name(self):
        """The current working or stored setup name."""
        return self.model.current_name

    @current_setup_name.setter
    def current_setup_name(self, value):
        value = str(value or "")
        if value in self.model.setups:
            self.select_setup(value)
        elif value != self.model.current_name:
            self.model.current_name = value
            self.model.data["setup_name"] = value
            self.editor.setup_name = value
            self.model.changed()

    setup_name = current_setup_name

    @property
    def current_setups_file(self):
        """The named-setup store path, independent of a working-definition input file."""
        return self.model.file_path

    @current_setups_file.setter
    def current_setups_file(self, value):
        self.model.file_path = str(value) if value is not None else None
        self.editor.toolbar.reload()

    def available_setups(self):
        """Read and return the current named setup choices."""
        self.model.refresh_setups()
        return tuple(self.model.setups)

    def select_setup(self, name):
        """Adopt the named setup through the existing native toolbar/model."""
        self.editor.toolbar.select(str(name))

    def read_tttr(self, path):
        """Start the existing asynchronous native read without blocking the GUI thread."""
        self.editor.read(str(path))
        self.app.request_frame()

    @property
    def read_running(self):
        """Whether a native measurement read is still pending."""
        return self.editor._future is not None

    def poll_read(self):
        """Publish a completed native read and its model/caller notification."""
        self.editor.poll()

    def set_microtime_per_channel_data(self, values, file_path=None):
        """Adopt already computed raw-channel preview histograms without another file read."""
        self.model.preview = {int(ch): np.asarray(counts, dtype=float).ravel().copy()
                              for ch, counts in (values or {}).items()}
        if file_path is not None:
            self.model.preview_path = str(file_path)
        self.model.data["_microtime_per_channel_decay"] = {
            "file_path": self.model.preview_path,
            "channels": {str(ch): counts.tolist() for ch, counts in self.model.preview.items()},
        }
        self.model.changed()
        self.app.request_frame()

    def set_microtime_data(self, counts, file_path=None):
        """Adopt a single already computed preview histogram at routing channel zero."""
        values = {0: counts} if counts is not None else {}
        self.set_microtime_per_channel_data(values, file_path)

    def get_preview(self):
        """Return copies of the currently displayed routing-channel histograms."""
        return {ch: counts.copy() for ch, counts in self.model.preview.items()}

    def closeEvent(self, event):
        """Delegate native cleanup to its owning ControlHost once and detach the callback."""
        self._close_native()
        super().closeEvent(event)

    def _close_native(self):
        """Detach the owned model callback and close its actual ControlHost once."""
        if not self._closed:
            self._closed = True
            if self.model.on_changed == self._owned_callback:
                self.model.on_changed = self._previous_callback
            self.host.close()


class DetectorWizard(QtWidgets.QWizard):
    """Retained wizard navigation around the single native detector page."""

    def __init__(self, json_file=None, **kwargs):
        """Keep old wizard defaults while hosting the native page only."""
        parent = kwargs.pop("parent", None)
        super().__init__(parent)
        kwargs.setdefault("show_edit_json", True)
        kwargs.setdefault("show_save", True)
        self.detector_page = DetectorWizardPage(json_file, self, **kwargs)
        self.addPage(self.detector_page)
        self.setWindowTitle(tr("Detector Configuration Wizard"))

    def closeEvent(self, event):
        """Close the owned native page before its existing wizard shell."""
        super().closeEvent(event)
        if event.isAccepted():
            self.detector_page.close()


__all__ = ["DetectorWizardPage", "DetectorWizard"]
