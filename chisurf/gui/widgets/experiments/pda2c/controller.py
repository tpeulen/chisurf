"""The Qt panel of the PDA reader (legacy; the emtk shell draws the same sections natively).

``pda.view.json`` is rendered by AutoForm; its three custom sections
(``pda_detector``, ``pda_tw``, ``pda_files``) are the layout widgets below. All
logic -- which detector a row takes, what a channel or window field means, the
time-window list, the file list and how files and burst tables are resolved --
lives Qt-free in :mod:`chisurf.core.experiments.pda2c.settings` and
:mod:`chisurf.core.experiments.pda2c.inputs`; this panel shows it and pushes
edits into it.
"""

import pathlib

import tttrlib

import chisurf as cs
from chisurf import logging
from chisurf.core.experiments.core import reader
from chisurf.core.experiments.pda2c import Pda2cReader, inputs
from chisurf.core.experiments.pda2c.settings import PdaReaderSettings
from chisurf.core.support.i18n import tr
from chisurf.gui import QtCore, QtWidgets, dialogs
from chisurf.gui.progress import ChiSurfProgress
from chisurf.gui.widgets.sample_picker import show_sample_picker_dialog
from chisurf.macros import core_data as core_data_macros


class _PdaDetectorWidget(QtWidgets.QWidget):
    """Container for the PDA detector cascade (Setup / Routine / one row per colour).

    The number of detector rows follows the reader's ``n_colors`` setting --
    three-colour PDA is a setting of the PDA experiment, not an experiment of
    its own, and the setting is what decides whether a burst becomes a row of an
    S1S2 histogram or a row of a five-column photon table.

    The micro-time fields mean different things at the two colour counts, so
    they are not laid out the same way. With two colours each detector has its
    own photon-selection window and the field sits on its row. With three the
    windows are the **excitation periods** of the PIE cycle: the blue pulse is
    seen in all three detectors and the green pulse in two, so a window belongs
    to no single detector and gets its own labelled row.

    This is a pure layout widget: it builds and exposes the combo boxes and line
    edits as ``detector_combos`` / ``channel_edits`` / ``window_edits``. All
    wiring lives on the controller, which grabs the child widgets via
    ``findChildren`` after AutoForm builds this.
    """

    def _configured(self, attr: str, defaults, render) -> list:
        """Return field texts for *attr*, falling back to *defaults* per row.

        Parameters
        ----------
        attr : str
            Reader attribute holding one entry per row (``channels``,
            ``micro_time_ranges``).
        defaults : sequence of str
            Field text used where the reader has no entry.
        render : callable
            Turns one entry into field text.

        Returns
        -------
        list of str
            One text per default, in row order.
        """
        values = list(getattr(self._model, attr, None) or [])
        # An entry the reader has but left empty stays empty: that is a colour
        # whose detector nobody has chosen yet (see
        # ``Pda2cReader.default_channels``), and filling it with a default would
        # hand the user a plausible wrong channel.
        return [
            render(values[index]) if index < len(values) else default
            for index, default in enumerate(defaults)
        ]

    def __init__(self, model, target=None, parent=None, **kwargs):
        super().__init__(parent)
        self._model = model
        self.n_colors = inputs.colour_count(getattr(model, "n_colors", 2))

        labels = inputs.COLOUR_LABELS[self.n_colors]
        # Start from what the reader is configured with, so the panel and the
        # reader agree before anything is touched.
        channels = self._configured(
            "channels", inputs.COLOUR_CHANNELS[self.n_colors], inputs.format_channels
        )
        windows = self._configured(
            "micro_time_ranges",
            inputs.COLOUR_WINDOWS[self.n_colors],
            inputs.format_micro_time_ranges,
        )

        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(0, 2, 0, 2)
        grid.setSpacing(3)

        grid.addWidget(QtWidgets.QLabel(tr("Setup:")), 0, 0)
        self.comboBox_setup = QtWidgets.QComboBox()
        grid.addWidget(self.comboBox_setup, 0, 1, 1, 3)

        grid.addWidget(QtWidgets.QLabel(tr("Routine:")), 1, 0)
        self.comboBox = QtWidgets.QComboBox()
        self.comboBox.insertItems(0, tttrlib.TTTR.get_supported_container_names())
        grid.addWidget(self.comboBox, 1, 1, 1, 3)

        grid.addWidget(QtWidgets.QLabel(tr("Detector")), 2, 1)
        grid.addWidget(QtWidgets.QLabel(tr("Channels")), 2, 2)
        if self.n_colors == 2:
            grid.addWidget(QtWidgets.QLabel(tr("Micro time")), 2, 3)

        self.detector_combos = []
        self.channel_edits = []
        self.window_edits = []

        for index, label in enumerate(labels):
            row = 3 + index
            grid.addWidget(QtWidgets.QLabel(f"{tr(label)}:"), row, 0)
            combo = QtWidgets.QComboBox()
            grid.addWidget(combo, row, 1)
            self.detector_combos.append(combo)
            edit = QtWidgets.QLineEdit(channels[index])
            edit.setToolTip(
                tr("Routing channels of the {colour} detector, comma separated.").format(
                    colour=tr(label).lower()
                )
            )
            grid.addWidget(edit, row, 2)
            self.channel_edits.append(edit)
            if self.n_colors == 2:
                window = QtWidgets.QLineEdit(windows[index])
                window.setToolTip(
                    tr(
                        "Micro-time ranges for the {colour} detector: start-end; "
                        "separate multiple ranges with ';'."
                    ).format(colour=tr(label).lower())
                )
                grid.addWidget(window, row, 3)
                self.window_edits.append(window)

        if self.n_colors == 3:
            row = 3 + len(labels)
            grid.addWidget(QtWidgets.QLabel(tr("Excitation:")), row, 0)
            excitation = QtWidgets.QWidget()
            box = QtWidgets.QHBoxLayout(excitation)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(3)
            for label, default in zip(inputs.EXCITATION_LABELS, windows):
                caption = QtWidgets.QLabel(tr(label))
                window = QtWidgets.QLineEdit(default)
                window.setToolTip(
                    tr(
                        "Micro-time range of the {colour} excitation period. Photons inside it "
                        "are counted in every detector that can see the {colour} pulse."
                    ).format(colour=tr(label).lower())
                )
                box.addWidget(caption)
                box.addWidget(window, 1)
                self.window_edits.append(window)
            grid.addWidget(excitation, row, 1, 1, 3)

        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)


class _PdaTimeWindowWidget(QtWidgets.QWidget):
    """Container for the PDA time-window controls (TW spin, add, list, auto-load)."""

    def __init__(self, model, target=None, parent=None, **kwargs):
        super().__init__(parent)
        self._model = model

        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(0, 2, 0, 2)
        grid.setSpacing(3)

        grid.addWidget(QtWidgets.QLabel(tr("TW [ms]:")), 0, 0)
        self.toolButton_add_tw = QtWidgets.QToolButton()
        self.toolButton_add_tw.setText("+")
        grid.addWidget(self.toolButton_add_tw, 0, 1)
        self.doubleSpinBox = QtWidgets.QDoubleSpinBox()
        self.doubleSpinBox.setRange(0.01, 9999.0)
        self.doubleSpinBox.setValue(2.0)
        grid.addWidget(self.doubleSpinBox, 0, 2)
        self.checkBox = QtWidgets.QCheckBox(tr("Auto load"))
        self.checkBox.setChecked(True)
        grid.addWidget(self.checkBox, 0, 3)

        self.listWidget_tw = QtWidgets.QListWidget()
        self.listWidget_tw.setMaximumHeight(80)
        self.listWidget_tw.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        grid.addWidget(self.listWidget_tw, 1, 0, 1, 4)

        grid.setColumnStretch(2, 1)


class DropFileList(QtWidgets.QListWidget):
    """The PDA file list: a view of :meth:`PdaReaderSettings.file_rows` that takes drops.

    Only the first :attr:`max_visible_items` entries become list items, so that
    dropping thousands of files cannot overload the widget; a summary row counts
    the rest, which are read like ticked ones.
    """

    max_visible_items = 128

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings: PdaReaderSettings | None = None
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
        self.setDefaultDropAction(QtCore.Qt.CopyAction)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.itemChanged.connect(self._on_item_changed)

    def sync(self) -> None:
        """Rebuild the items from the settings' file list."""
        self.blockSignals(True)
        try:
            self.clear()
            rows = self.settings.file_rows() if self.settings is not None else []
            for row in rows[: self.max_visible_items]:
                item = QtWidgets.QListWidgetItem(row["path"])
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.Checked if row["use"] else QtCore.Qt.Unchecked)
                self.addItem(item)
            extra = len(rows) - self.max_visible_items
            if extra > 0:
                summary = QtWidgets.QListWidgetItem(
                    tr("... and {n} more file(s) not shown").format(n=extra)
                )
                summary.setFlags(QtCore.Qt.NoItemFlags)
                self.addItem(summary)
        finally:
            self.blockSignals(False)

    def _on_item_changed(self, item) -> None:
        if self.settings is not None:
            self.settings.set_use(item.text(), item.checkState() == QtCore.Qt.Checked)

    def add_paths(self, paths) -> int:
        """Add dropped paths through the settings; returns how many were taken."""
        added = self.settings.add_paths(paths) if self.settings is not None else 0
        self.sync()
        return added

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
        event.acceptProposedAction()
        if self.add_paths(paths) and self.settings is not None and self.settings.auto_load:
            # Load on the event loop, not inside dropEvent: reading many files
            # re-entrantly in a drop handler destabilises the drag machinery.
            owner = self.parent()
            while owner is not None and not hasattr(owner, "_on_load_dropped_files_clicked"):
                owner = owner.parent()
            if owner is not None:
                QtCore.QTimer.singleShot(0, owner._on_load_dropped_files_clicked)

    def remove_selected(self):
        """Remove the selected entries."""
        if self.settings is not None:
            chosen = self.selectedItems()
            self.settings.remove_paths(
                item.text() for item in chosen if item.flags() != QtCore.Qt.NoItemFlags
            )
        self.sync()

    def clear_all(self):
        """Remove every entry."""
        if self.settings is not None:
            self.settings.clear_files()
        self.sync()

    def get_all_paths(self):
        """Every entry, ticked or not."""
        return [row["path"] for row in self.settings.file_rows()] if self.settings else []

    def get_checked_paths(self):
        """The ticked entries: what a load reads."""
        return self.settings.checked_paths() if self.settings is not None else []

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu(self)
        act_delete = menu.addAction(tr("Delete selected"))
        act_clear = menu.addAction(tr("Clear all"))
        chosen = menu.exec_(event.globalPos())
        if chosen == act_delete:
            self.remove_selected()
        elif chosen == act_clear:
            self.clear_all()


class _PdaFilesWidget(QtWidgets.QWidget):
    """Container for the PDA file list: a caption, the drop list, *Load dropped files* and *Clear*."""

    def __init__(self, model, target=None, parent=None, **kwargs):
        super().__init__(parent)
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(0, 2, 0, 2)
        box.setSpacing(2)
        self.drop_label = QtWidgets.QLabel(tr("Drop files or analysis folders below"))
        self.drop_label.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.drop_label.setToolTip(
            tr(
                "Drag and drop TTTR files, BID/BUR/BST files, or burst analysis folders "
                "(bi4_bur). Checked files are used."
            )
        )
        box.addWidget(self.drop_label)
        self.file_list = DropFileList(self)
        self.file_list.setMinimumHeight(120)
        box.addWidget(self.file_list, 1)
        row = QtWidgets.QHBoxLayout()
        self.load_button = QtWidgets.QPushButton(tr("Load dropped files"))
        self.load_button.setToolTip(tr("Read checked TTTR files using current PDA settings"))
        row.addWidget(self.load_button)
        self.clear_button = QtWidgets.QPushButton(tr("Clear"))
        self.clear_button.setToolTip(tr("Clear all dropped files from the list"))
        row.addWidget(self.clear_button)
        row.addStretch(1)
        box.addLayout(row)


def _register_pda_sections() -> None:
    from chisurf.gui.autoform.sections.registry import register_section

    register_section("pda_detector")(_PdaDetectorWidget)
    register_section("pda_tw")(_PdaTimeWindowWidget)
    register_section("pda_files")(_PdaFilesWidget)


class Pda2cTTTRWidget(QtWidgets.QWidget, reader.ExperimentReaderController):
    """The PDA reader's Qt panel over :class:`PdaReaderSettings`."""

    def __init__(self, *args, **kwargs):
        _register_pda_sections()
        super().__init__(*args, **kwargs)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(2)

        # QAction keeps backward compat with .ui-based signal wiring
        self.actionParametersChanged = QtWidgets.QAction(self)
        self.actionParametersChanged.triggered.connect(self.onParametersChanged)

        reader_obj = self.experiment_reader
        # The settings first: choosing the setup writes its detectors onto the
        # reader, so the form below is built with the rows it will read with.
        self.pda_settings = PdaReaderSettings(reader_obj) if reader_obj is not None else None

        self._settings_form = None
        if reader_obj is not None and hasattr(reader_obj, "view_spec"):
            from chisurf.gui.autoform import AutoForm

            self._settings_form = AutoForm(reader_obj, parent=self)
            main_layout.addWidget(self._settings_form)

        self._grab_section_refs()
        self._wire_section_widgets()
        # Switching the colour count rebuilds the whole form (the choice section
        # is declared ``rebuild_on_change``), which deletes every widget grabbed
        # above. Without re-grabbing, the next parameter change would reach into
        # a destroyed C++ object.
        if self._settings_form is not None:
            self._settings_form.rebuilt.connect(self._on_form_rebuilt)
        self._refresh_all()

    # ---- the custom-section widgets ----
    def _grab_section_refs(self) -> None:
        """Expose the AutoForm-built custom-section child widgets as attributes.

        The detector rows are lists rather than numbered attributes, because how
        many of them exist is the colour-count setting.
        """
        self.detector_combos = []
        self.channel_edits = []
        self.window_edits = []
        if self._settings_form is None:
            return
        det = self._settings_form.findChildren(_PdaDetectorWidget)
        if det:
            d = det[0]
            self.comboBox_setup = d.comboBox_setup
            self.comboBox = d.comboBox
            self.detector_combos = list(d.detector_combos)
            self.channel_edits = list(d.channel_edits)
            self.window_edits = list(d.window_edits)
        tw = self._settings_form.findChildren(_PdaTimeWindowWidget)
        if tw:
            t = tw[0]
            self.doubleSpinBox = t.doubleSpinBox
            self.toolButton_add_tw = t.toolButton_add_tw
            self.checkBox = t.checkBox
            self.listWidget_tw = t.listWidget_tw
        files = self._settings_form.findChildren(_PdaFilesWidget)
        if files:
            f = files[0]
            self.drop_label = f.drop_label
            self.file_list = f.file_list
            self.file_list.settings = self.pda_settings
            self.load_button = f.load_button
            self.clear_button = f.clear_button

    def _wire_section_widgets(self) -> None:
        """Connect the freshly built custom-section widgets to the handlers."""
        if self._settings_form is None:
            return
        self.comboBox.currentTextChanged.connect(self.actionParametersChanged.trigger)
        self.comboBox_setup.currentTextChanged.connect(self._on_setup_changed)
        for combo in self.detector_combos:
            combo.currentTextChanged.connect(self._on_detector_combo_changed)
        for edit in self.channel_edits + self.window_edits:
            edit.editingFinished.connect(self.actionParametersChanged.trigger)
        self.doubleSpinBox.valueChanged.connect(self.actionParametersChanged.trigger)
        self.checkBox.toggled.connect(self._on_auto_load_toggled)

        self.toolButton_add_tw.clicked.connect(self._on_add_tw_clicked)
        self.listWidget_tw.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.listWidget_tw.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.listWidget_tw.customContextMenuRequested.connect(self._on_tw_list_context_menu)
        self.listWidget_tw.itemDoubleClicked.connect(self._on_tw_item_double_clicked)

        if hasattr(self, "file_list"):
            self.load_button.clicked.connect(self._on_load_dropped_files_clicked)
            self.clear_button.clicked.connect(self.file_list.clear_all)

    def _on_form_rebuilt(self) -> None:
        """Re-adopt the custom-section widgets after AutoForm rebuilt the panel.

        A rebuild is how the colour count takes effect: the detector section
        comes back with a different number of rows. The rows, the time windows
        and the file list live on the reader, so they come back as they were.
        """
        self._grab_section_refs()
        self._wire_section_widgets()
        if self.pda_settings is not None:
            self.pda_settings.sync()
        self._refresh_all()

    def _refresh_all(self) -> None:
        """Show what the reader holds: setups, routine, rows, time windows, auto-load, files."""
        if self.pda_settings is None or self._settings_form is None:
            return
        self._load_available_setups_into_combobox()
        self._populate_detector_combos()
        self._refresh_rows()
        self._refresh_tw_list()
        self.doubleSpinBox.blockSignals(True)
        if self.pda_settings.tw_ms > 0.0:
            self.doubleSpinBox.setValue(self.pda_settings.tw_ms)
        self.doubleSpinBox.blockSignals(False)
        self.checkBox.blockSignals(True)
        self.checkBox.setChecked(self.pda_settings.auto_load)
        self.checkBox.blockSignals(False)
        if hasattr(self, "file_list"):
            self.file_list.sync()

    def _db(self):
        """Return the MMFDB connection from the current reader when available."""
        try:
            return self.db
        except Exception:
            return None

    def _select_sample_id(self) -> str | None:
        """Prompt the user for a sample before loading dropped files."""
        return show_sample_picker_dialog(db=self._db(), parent=self)

    # ---- setup, routine and detector rows ----
    def _load_available_setups_into_combobox(self):
        self.comboBox_setup.blockSignals(True)
        self.comboBox_setup.clear()
        self.comboBox_setup.addItems(self.pda_settings.setup_names())
        self.comboBox_setup.setCurrentText(self.pda_settings.setup)
        self.comboBox_setup.blockSignals(False)

    def _on_setup_changed(self, name: str):
        self.pda_settings.setup = name
        self._populate_detector_combos()
        self._refresh_rows()
        self.actionParametersChanged.trigger()

    @property
    def n_colors(self) -> int:
        """Number of detection colours the reader is configured for (2 or 3)."""
        return inputs.colour_count(getattr(self.experiment_reader, "n_colors", 2))

    def _populate_detector_combos(self):
        """Fill one detector combo per colour with the setup's detectors, the row's chosen."""
        names = self.pda_settings.detector_names()
        for index, combo in enumerate(self.detector_combos):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names or [""])
            if names:
                combo.setCurrentText(self.pda_settings.detector(index))
            combo.blockSignals(False)

    def _on_detector_combo_changed(self, _):
        for index, combo in enumerate(self.detector_combos):
            if combo.currentText() and combo.currentText() != self.pda_settings.detector(index):
                self.pda_settings.set_detector(index, combo.currentText())
        self._refresh_rows()
        self.actionParametersChanged.trigger()

    def _refresh_rows(self) -> None:
        """Show the reader's routine, routing channels and micro-time windows in the row fields."""
        routine = self.pda_settings.routine
        if routine:
            self.comboBox.blockSignals(True)
            self.comboBox.setCurrentText(routine)
            self.comboBox.blockSignals(False)
        for index, edit in enumerate(self.channel_edits):
            edit.setText(self.pda_settings.channels_text(index))
        for index, edit in enumerate(self.window_edits):
            edit.setText(self.pda_settings.window_text(index))

    def updateUI(self):
        """Update UI elements based on the bound reader's properties."""
        if self.pda_settings is not None:
            self._refresh_all()

    def onParametersChanged(self):
        """Push the field texts, routine and time window onto the reader."""
        if self.pda_settings is None or self._settings_form is None:
            return
        self.pda_settings.routine = self.comboBox.currentText()
        for index, edit in enumerate(self.channel_edits):
            self.pda_settings.set_channels_text(index, edit.text())
        for index, edit in enumerate(self.window_edits):
            self.pda_settings.set_window_text(index, edit.text())
        self.pda_settings.tw_ms = float(self.doubleSpinBox.value())

    def _on_auto_load_toggled(self, checked: bool) -> None:
        self.pda_settings.auto_load = bool(checked)

    # ---- time windows ----
    def _refresh_tw_list(self) -> None:
        """Show the reader's time windows in the list."""
        self.listWidget_tw.clear()
        for row in self.pda_settings.tw_rows():
            item = QtWidgets.QListWidgetItem(row["window"])
            item.setData(QtCore.Qt.UserRole, (row["n_ph"], row["tw_s"]))
            self.listWidget_tw.addItem(item)

    def _on_add_tw_clicked(self):
        self.pda_settings.tw_ms = float(self.doubleSpinBox.value())
        self.pda_settings.add_tw()
        self._refresh_tw_list()

    def _remove_tw_rows(self, rows) -> None:
        for row in sorted(set(rows), reverse=True):
            self.pda_settings.remove_tw(row)
        self._refresh_tw_list()

    def _on_tw_item_double_clicked(self, item):
        if item is not None:
            self._remove_tw_rows([self.listWidget_tw.row(item)])

    def _on_tw_list_context_menu(self, pos):
        menu = QtWidgets.QMenu(self.listWidget_tw)
        act_remove = menu.addAction(tr("Remove selected"))
        act_clear = menu.addAction(tr("Clear all"))
        chosen = menu.exec_(self.listWidget_tw.mapToGlobal(pos))
        if chosen == act_remove:
            selected = self.listWidget_tw.selectedItems()
            self._remove_tw_rows(self.listWidget_tw.row(i) for i in selected)
        elif chosen == act_clear:
            self.pda_settings.clear_tw()
            self._refresh_tw_list()

    # ---- loading ----
    def get_filename(self) -> pathlib.Path:
        return cs.gui.widgets.open_files(
            description="HT3/PTU/SPC file", file_type="All files (*.*)", working_path=None
        )

    def _reader_for_load(self) -> Pda2cReader:
        """A reader with the panel's settings, for one load of the file list."""
        self.onParametersChanged()
        bound = self.experiment_reader
        pda_reader = Pda2cReader(
            channels=list(bound.channels),
            micro_time_ranges=list(bound.micro_time_ranges or []),
            reading_routine=bound.reading_routine,
            maximum_number_of_photons=int(bound.maximum_number_of_photons or 500),
            minimum_number_of_photons=int(bound.minimum_number_of_photons or 15),
            minimum_time_window_length=float(bound.minimum_time_window_length or 0.0),
            tw_configs=self.pda_settings.tw_configs(),
            n_colors=self.n_colors,
            segmentation=getattr(bound, "segmentation", "burst"),
        )
        # get_data sets d.experiment from the reader's experiment.
        experiment = getattr(bound, "experiment", None)
        pda_reader.experiment = experiment or cs.core.experiments.types.get("pda")
        pda_reader.controller = self
        return pda_reader

    def _on_load_dropped_files_clicked(self):
        files = self.file_list.get_checked_paths() if hasattr(self, "file_list") else []
        if not files:
            logging.warning("PDA: No dropped files are checked to load.")
            dialogs.information(self, tr("No files"), tr("No dropped files are checked to load."))
            return
        exts = inputs.tttr_extensions()
        bur_files, tttr_files = inputs.classify_inputs(files, exts)
        try:
            tttr_files, notes = inputs.check_input_counts(bur_files, tttr_files)
        except inputs.PdaInputError as exc:
            logging.warning("PDA: %s", exc)
            dialogs.warning(self, tr(exc.title), str(exc))
            return
        for title, message in notes:
            dialogs.warning(self, tr(title), message)

        pda_reader = self._reader_for_load()
        pda_reader.sample_id = self._select_sample_id()

        parent = getattr(cs, "cs", None)
        if not isinstance(parent, QtWidgets.QWidget):
            parent = self.window()
        progress_dialog = ChiSurfProgress(
            parent, tr("Preparing dropped files..."), 0, title=tr("Loading PDA data")
        )
        try:
            if bur_files:
                progress_dialog.setRange(0, max(1, len(bur_files)))
                progress_dialog.update_progress(0, tr("Resolving BUR files..."))

            def _progress(i, total, current):
                """Show resolving progress; ``False`` when the user cancelled."""
                progress_dialog.update_progress(
                    i,
                    tr("Resolving: {name} ({i}/{total})").format(
                        name=pathlib.Path(current).name, i=i, total=total
                    ),
                )
                QtWidgets.QApplication.processEvents()
                return not progress_dialog.wasCanceled()

            try:
                resolved = inputs.resolve_classified(bur_files, tttr_files, exts, _progress)
            except inputs.PdaInputError as exc:
                logging.warning("PDA: %s", exc)
                dialogs.warning(self, tr(exc.title), str(exc))
                return
            for title, message in resolved.warnings:
                dialogs.warning(self, tr(title), message)
            if resolved.burst_slices:
                total = sum(len(v) for v in resolved.burst_slices.values())
                logging.info(
                    "PDA: burst slicing from BUR files: %d slices across %d file(s).",
                    total,
                    len(resolved.burst_slices),
                )
            progress_dialog.setRange(0, 0)
            progress_dialog.update_progress(0, tr("Loading TTTR data and computing histograms..."))
            QtWidgets.QApplication.processEvents()
            core_data_macros.add_dataset(
                experiment_reader=pda_reader,
                filename="|".join(resolved.tttr_files),
                burst_slices=resolved.burst_slices,
            )
            if self.pda_settings.auto_load:
                self.file_list.clear_all()
        except Exception as e:
            logging.warning(f"PDA: Failed to load files: {e}")
            dialogs.error(self, tr("Error"), tr("Failed to load files: {error}").format(error=e))
        finally:
            progress_dialog.finish(final_text=None, auto_close=True, close_delay_ms=0)
