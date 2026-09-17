from __future__ import annotations

import pathlib

import numpy as np

import chisurf as cs
from chisurf.gui import QtWidgets
from chisurf.gui import chiplot as cp
from chisurf.gui.widgets.collapsible_box import CollapsibleBox


class TCSPCSimulatorSetupWidget(QtWidgets.QWidget):
    """Controller widget for the TCSPC simulator reader.

    This widget exposes the simulator parameters (sample name, lifetime
    spectrum, number of TAC channels, peak count, dt) and a small preview
    plot. It also provides:

    - An IRF selector with Gaussian fallback.
    - A **Simulate** button to generate a Poisson-noisy decay.
    - An **Add** button to append the simulated decay to
      ``cs.imported_datasets``.
    - A tool button next to the *lifetime spectrum* field that loads an
      interleaved (amplitude, lifetime, ...) spectrum from a CSV/text file
      into the line edit.
    """

    @cs.gui.decorators.init_with_ui("tcspc_simulator.ui")
    def __init__(self, *args, **kwargs):
        # Internal reference to the currently selected IRF dataset (if any)
        self._irf_dataset = None

        # Lifetime spectrum loader button next to the line edit.
        # We wrap the existing lineEdit_2 into a small row layout together
        # with a tool button so the .ui file does not need to change.
        try:
            le_lt = self.lineEdit_2
        except Exception:
            le_lt = None
        if le_lt is not None:
            try:
                grid = self.gridLayout
            except Exception:
                grid = None
            if isinstance(grid, QtWidgets.QGridLayout):
                try:
                    idx = grid.indexOf(le_lt)
                except Exception:
                    idx = -1
                if idx >= 0:
                    try:
                        row, col, row_span, col_span = grid.getItemPosition(idx)
                    except Exception:
                        row, col, row_span, col_span = 1, 1, 1, 1

                    # Remove from grid and put into a small container with a button.
                    grid.removeWidget(le_lt)
                    container = QtWidgets.QWidget(self)
                    hl = QtWidgets.QHBoxLayout(container)
                    hl.setContentsMargins(0, 0, 0, 0)
                    hl.setSpacing(2)
                    hl.addWidget(le_lt, 1)

                    self.toolButton_load_lifetime = QtWidgets.QToolButton(container)
                    self.toolButton_load_lifetime.setText("...")
                    self.toolButton_load_lifetime.setToolTip(
                        "Load lifetime spectrum from CSV/text file"
                    )
                    hl.addWidget(self.toolButton_load_lifetime, 0)

                    grid.addWidget(container, row, col, row_span, col_span)

                    try:
                        self.toolButton_load_lifetime.clicked.connect(
                            self._on_load_lifetime_clicked
                        )
                    except Exception:
                        pass

        # Hidden IRF selector window (shown on button click, similar to ConvolveWidget)
        # Do not pass a concrete Experiment instance as filter here; this would
        # break isinstance checks in ExperimentalDataSelector. Leaving
        # "experiment" unset mirrors ConvolveWidget behaviour and shows the
        # same imported datasets.
        self.irf_selector = cs.gui.widgets.experiments.ExperimentalDataSelector(
            click_close=True,
            parent=None,
            context_menu_enabled=False,
            change_event=self._on_irf_selection_changed,
        )

        # IRF selection row: label + "Select IRF" button
        irf_select_layout = QtWidgets.QHBoxLayout()
        irf_select_layout.setContentsMargins(0, 0, 0, 0)
        irf_select_layout.setSpacing(2)

        self.label_irf_source = QtWidgets.QLabel(
            "IRF: Gaussian (no dataset selected)",
            self,
        )
        irf_select_layout.addWidget(self.label_irf_source, 1)

        self.toolButton_select_irf = QtWidgets.QToolButton(self)
        self.toolButton_select_irf.setText("Select IRF")
        self.toolButton_select_irf.setToolTip("Select IRF dataset from imported TCSPC curves")
        irf_select_layout.addWidget(self.toolButton_select_irf)

        self.toolButton_unload_irf = QtWidgets.QToolButton(self)
        self.toolButton_unload_irf.setText("X")
        self.toolButton_unload_irf.setToolTip("Unload IRF and use Gaussian")
        irf_select_layout.addWidget(self.toolButton_unload_irf)

        self.verticalLayout_2.addLayout(irf_select_layout)

        # Gaussian fallback IRF parameters (used when no IRF dataset is selected)
        irf_gauss_layout = QtWidgets.QHBoxLayout()
        irf_gauss_layout.setContentsMargins(0, 0, 0, 0)
        irf_gauss_layout.setSpacing(2)
        irf_gauss_layout.addWidget(QtWidgets.QLabel("Gaussian IRF mean [ns]:"))
        self.doubleSpinBox_irf_mean = QtWidgets.QDoubleSpinBox(self)
        self.doubleSpinBox_irf_mean.setDecimals(3)
        self.doubleSpinBox_irf_mean.setRange(-1000.0, 1000.0)
        self.doubleSpinBox_irf_mean.setValue(5.0)
        irf_gauss_layout.addWidget(self.doubleSpinBox_irf_mean)
        irf_gauss_layout.addWidget(QtWidgets.QLabel("sigma [ns]:"))
        self.doubleSpinBox_irf_sigma = QtWidgets.QDoubleSpinBox(self)
        self.doubleSpinBox_irf_sigma.setDecimals(3)
        self.doubleSpinBox_irf_sigma.setRange(1e-4, 1000.0)
        self.doubleSpinBox_irf_sigma.setValue(0.2)
        irf_gauss_layout.addWidget(self.doubleSpinBox_irf_sigma)
        irf_gauss_layout.addStretch(1)
        self.verticalLayout_2.addLayout(irf_gauss_layout)

        # Keep the setup compact: decay and anisotropy are independent editing
        # surfaces, so give each its own tab.  The shared AutoForm foldable is
        # used for the section headers rather than another bespoke group-box
        # implementation.
        self.verticalLayout.removeWidget(self.groupBox)
        self.decay_tab = QtWidgets.QWidget(self)
        decay_tab_layout = QtWidgets.QVBoxLayout(self.decay_tab)
        decay_tab_layout.setContentsMargins(0, 0, 0, 0)
        self.decay_section = CollapsibleBox(
            "Decay parameters", self.decay_tab, expanded=True, auto_fold=False
        )
        self.groupBox.setTitle("")
        self.decay_section.add_widget(self.groupBox)
        decay_tab_layout.addWidget(self.decay_section)
        decay_tab_layout.addStretch(1)

        self.settings_tabs = QtWidgets.QTabWidget(self)
        self.settings_tabs.addTab(self.decay_tab, "Decay")

        # -- Anisotropy: VM vs VV/VH --------------------------------------
        aniso_group = QtWidgets.QGroupBox("Anisotropy", self)
        aniso_layout = QtWidgets.QVBoxLayout(aniso_group)
        aniso_layout.setContentsMargins(0, 0, 0, 0)
        aniso_layout.setSpacing(2)
        mode_layout = QtWidgets.QHBoxLayout()
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.addWidget(QtWidgets.QLabel("Mode:"))
        self.comboBox_polarization = QtWidgets.QComboBox(aniso_group)
        self.comboBox_polarization.addItem("VM (magic angle)", "vm")
        self.comboBox_polarization.addItem("VV/VH (polarized)", "vv/vh")
        mode_layout.addWidget(self.comboBox_polarization, 1)
        aniso_layout.addLayout(mode_layout)
        corr_layout = QtWidgets.QHBoxLayout()
        corr_layout.setContentsMargins(0, 0, 0, 0)
        for attr, label, value in (
            ("doubleSpinBox_g_factor", "g:", 1.0),
            ("doubleSpinBox_l1", "l1:", 0.0),
            ("doubleSpinBox_l2", "l2:", 0.0),
        ):
            spin = QtWidgets.QDoubleSpinBox(aniso_group)
            spin.setDecimals(4)
            if attr == "doubleSpinBox_g_factor":
                # g is a sensitivity *ratio*: strictly positive.
                spin.setRange(0.0001, 100.0)
            else:
                spin.setRange(-10.0, 10.0)
            spin.setValue(value)
            spin.setToolTip(
                {
                    attr: "Parallel/perpendicular detection sensitivity ratio.",
                    "doubleSpinBox_l1": "Mixing factor of the parallel (VV) channel.",
                    "doubleSpinBox_l2": "Mixing factor of the perpendicular (VH) channel.",
                }[attr]
            )
            corr_layout.addWidget(QtWidgets.QLabel(label))
            corr_layout.addWidget(spin)
            setattr(self, attr, spin)
        aniso_layout.addLayout(corr_layout)
        rot_layout = QtWidgets.QHBoxLayout()
        rot_layout.addWidget(QtWidgets.QLabel("Rotation b, ρ:"))
        self.lineEdit_rotation = QtWidgets.QLineEdit(aniso_group)
        self.lineEdit_rotation.setText("0.2, 1.0")
        rot_layout.addWidget(self.lineEdit_rotation, 1)
        aniso_layout.addLayout(rot_layout)
        # The extra aniso line: r(t) of the rotation spectrum, plotted in
        # both modes (on its own axis — the decay plot is log-counts).
        self.anisotropy_plot = cp.Plot(title="Anisotropy r(t)")
        self.anisotropy_plot.set_labels(bottom="Time (ns)", left="r(t)")
        try:
            self.anisotropy_plot.setMaximumHeight(130)
        except Exception:
            pass
        aniso_layout.addWidget(self.anisotropy_plot)
        self.aniso_tab = QtWidgets.QWidget(self)
        aniso_tab_layout = QtWidgets.QVBoxLayout(self.aniso_tab)
        aniso_tab_layout.setContentsMargins(0, 0, 0, 0)
        self.aniso_section = CollapsibleBox(
            "Anisotropy decay", self.aniso_tab, expanded=True, auto_fold=False
        )
        aniso_group.setTitle("")
        self.aniso_section.add_widget(aniso_group)
        aniso_tab_layout.addWidget(self.aniso_section)
        aniso_tab_layout.addStretch(1)
        self.settings_tabs.addTab(self.aniso_tab, "Anisotropy")
        # Simulation preview (simulate button + add button + plot)
        preview_group = QtWidgets.QWidget(self)
        preview_layout = QtWidgets.QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(0)
        header.addStretch(1)

        self.toolButton_simulate = QtWidgets.QToolButton(preview_group)
        self.toolButton_simulate.setText("Simulate")
        self.toolButton_simulate.setToolTip("Simulate TCSPC decay using current parameters")
        header.addWidget(self.toolButton_simulate)

        self.toolButton_add = QtWidgets.QToolButton(preview_group)
        self.toolButton_add.setText("Add")
        self.toolButton_add.setToolTip("Add simulated decay as dataset")
        header.addWidget(self.toolButton_add)

        self.simulation_plot = cp.Plot(title="Simulated TCSPC decay")
        self.simulation_plot.set_labels(bottom="Time (ns)", left="Counts")
        try:
            self.simulation_plot.set_log(y=True)
        except Exception:
            pass
        preview_layout.addWidget(self.simulation_plot)

        self.preview_tab = QtWidgets.QWidget(self)
        preview_tab_layout = QtWidgets.QVBoxLayout(self.preview_tab)
        preview_tab_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_section = CollapsibleBox(
            "Simulation preview", self.preview_tab, expanded=True, auto_fold=False
        )
        preview_tab_layout.addLayout(header)
        self.preview_section.add_widget(preview_group)
        preview_tab_layout.addWidget(self.preview_section)
        self.settings_tabs.addTab(self.preview_tab, "Preview")
        self.verticalLayout.addWidget(self.settings_tabs)

        # Internal state for last simulation
        self._sim_t = None
        self._sim_y = None
        self._sim_vv = None
        self._sim_vh = None

        # Anisotropy controls push into the setup like the .ui controls do
        # via actionParametersChanged.
        try:
            self.comboBox_polarization.currentIndexChanged.connect(self.onParametersChanged)
            self.doubleSpinBox_g_factor.valueChanged.connect(self.onParametersChanged)
            self.doubleSpinBox_l1.valueChanged.connect(self.onParametersChanged)
            self.doubleSpinBox_l2.valueChanged.connect(self.onParametersChanged)
            self.lineEdit_rotation.textChanged.connect(self.onParametersChanged)
        except Exception:
            pass

        self.actionParametersChanged.triggered.connect(self.onParametersChanged)
        try:
            self.toolButton_select_irf.clicked.connect(self._on_irf_button_clicked)
        except Exception:
            pass
        try:
            self.toolButton_unload_irf.clicked.connect(self._on_irf_unload_clicked)
        except Exception:
            pass
        try:
            self.toolButton_simulate.clicked.connect(self._on_simulate_clicked)
        except Exception:
            pass
        try:
            self.toolButton_add.clicked.connect(self._on_add_clicked)
        except Exception:
            pass

        self.onParametersChanged()

    def get_filename(self) -> pathlib.Path:
        return pathlib.Path(self.lineEdit.text())

    def updateUI(self):
        """Update UI elements based on current_setup properties."""
        # Get the current setup
        try:
            setup = cs.current_setup
        except Exception:
            return

        # Update sample_name line edit
        if hasattr(setup, "sample_name"):
            self.lineEdit.setText(setup.sample_name)

        # Update dt spin box
        if hasattr(setup, "dt"):
            self.doubleSpinBox.setValue(setup.dt)

        # Update n_tac spin box
        if hasattr(setup, "n_tac"):
            self.spinBox.setValue(setup.n_tac)

        # Update p0 spin box
        if hasattr(setup, "p0"):
            self.spinBox_2.setValue(int(setup.p0))

        # Update lifetime_spectrum line edit
        if hasattr(setup, "lifetime_spectrum"):
            lt = setup.lifetime_spectrum
            if isinstance(lt, np.ndarray):
                text = ", ".join(map(str, lt)) if lt.size > 0 else ""
            elif isinstance(lt, (list, tuple)):
                text = ", ".join(map(str, lt))
            elif lt is None:
                text = ""
            else:
                text = str(lt)
            self.lineEdit_2.setText(text)

        # Anisotropy state
        try:
            pol = str(getattr(setup, "polarization", "vm")).lower()
        except Exception:
            pol = "vm"
        try:
            idx = self.comboBox_polarization.findData("vv/vh" if pol != "vm" else "vm")
            if idx >= 0:
                self.comboBox_polarization.setCurrentIndex(idx)
        except Exception:
            pass
        try:
            self.doubleSpinBox_g_factor.setValue(float(getattr(setup, "g_factor", 1.0)))
            self.doubleSpinBox_l1.setValue(float(getattr(setup, "l1", 0.0)))
            self.doubleSpinBox_l2.setValue(float(getattr(setup, "l2", 0.0)))
        except Exception:
            pass
        try:
            rot = getattr(setup, "rotation_spectrum", None)
            if isinstance(rot, np.ndarray):
                text = ", ".join(map(str, rot)) if rot.size > 0 else ""
            elif isinstance(rot, (list, tuple)):
                text = ", ".join(map(str, rot))
            else:
                text = ""
            self.lineEdit_rotation.setText(text)
        except Exception:
            pass

    def onParametersChanged(self):
        try:
            setup = cs.current_setup
        except Exception:
            return
        if setup is None:
            return
        try:
            setup.sample_name = str(self.lineEdit.text())
            setup.dt = float(self.doubleSpinBox.value())
            setup.lifetime_spectrum = self._parse_lifetime_spectrum().astype(np.float64)
            setup.n_tac = int(self.spinBox.value())
            setup.p0 = int(self.spinBox_2.value())
            # The IRF settings belong to the setup as well: the *Read data*
            # header's **+ Data** button reads through ``setup.read()`` and must
            # see the same IRF as the panel's **Simulate**/**Add** buttons.
            setup.instrument_response_function = getattr(self, "_irf_dataset", None)
            setup.irf_mean = float(self.doubleSpinBox_irf_mean.value())
            setup.irf_sigma = float(self.doubleSpinBox_irf_sigma.value())
        except Exception:
            pass

        # Anisotropy: push into the setup. g/l1/l2 are this reader's own
        # calibration attributes, so a fit over an added VV/VH dataset reads
        # the corrections the simulation ran with — like a VV/VH file load.
        try:
            polarization = "vv/vh" if self.comboBox_polarization.currentData() == "vv/vh" else "vm"
            setup.polarization = polarization
            # ``is_vv_vh`` is the TCSPCReader property; its setter keeps the
            # use_header/dt_scaled bookkeeping consistent.
            setup.is_vv_vh = polarization != "vm"
            setup.g_factor = float(self.doubleSpinBox_g_factor.value())
            setup.l1 = float(self.doubleSpinBox_l1.value())
            setup.l2 = float(self.doubleSpinBox_l2.value())
            setup.rotation_spectrum = self._parse_rotation_spectrum().astype(np.float64)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Simulation & IRF handling
    # ------------------------------------------------------------------

    def _on_load_lifetime_clicked(self) -> None:
        """Load a lifetime spectrum from a CSV/text file into the line edit.

        The loader accepts either a flat 1D list of values or a
        two-column (amplitude, lifetime) table. In both cases the values
        are converted into the interleaved ``a1, tau1, a2, tau2, ...``
        string used by the simulator. The line edit is updated and
        :meth:`onParametersChanged` is called so ``gui.current_setup``
        reflects the new spectrum.
        """
        import numpy as _np
        from qtpy import QtWidgets as _QtWidgets

        try:
            start_dir = getattr(cs, "working_path", "") or ""
        except Exception:
            start_dir = ""

        fn, _ = _QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open lifetime spectrum (CSV/text)",
            str(start_dir),
            "Data files (*.csv *.txt *.dat);;All files (*)",
        )
        if not fn:
            return

        try:
            data = _np.loadtxt(fn, dtype=float, ndmin=1)
        except Exception:
            return

        values: _np.ndarray
        try:
            arr = _np.asarray(data, dtype=float)
        except Exception:
            return

        if arr.ndim == 1:
            values = arr
        elif arr.ndim == 2 and arr.shape[1] >= 2:
            # Use the first two columns as (amplitude, lifetime) pairs
            a = arr[:, 0].ravel()
            tau = arr[:, 1].ravel()
            n = min(a.size, tau.size)
            if n <= 0:
                return
            inter = _np.empty(2 * n, dtype=float)
            inter[0::2] = a[:n]
            inter[1::2] = tau[:n]
            values = inter
        else:
            return

        try:
            txt = ", ".join(f"{float(v):g}" for v in values)
        except Exception:
            return

        try:
            self.lineEdit_2.setText(txt)
        except Exception:
            return

        try:
            self.onParametersChanged()
        except Exception:
            pass

    def _parse_lifetime_spectrum(self) -> np.ndarray:
        """Parse the lifetime spectrum text into an interleaved numpy array."""
        text = self.lineEdit_2.text()
        parts = [p.strip() for p in str(text).replace(";", ",").split(",") if p.strip()]
        values = []
        for p in parts:
            try:
                values.append(float(p))
            except Exception:
                continue
        return np.asarray(values, dtype=float)

    def _parse_rotation_spectrum(self) -> np.ndarray:
        """Parse the rotation-spectrum text into an interleaved numpy array."""
        text = self.lineEdit_rotation.text()
        parts = [p.strip() for p in str(text).replace(";", ",").split(",") if p.strip()]
        values = []
        for p in parts:
            try:
                values.append(float(p))
            except Exception:
                continue
        return np.asarray(values, dtype=float)

    def _is_vvvh_mode(self) -> bool:
        """Return True when the mode combo selects the polarized VV/VH simulation."""
        try:
            return self.comboBox_polarization.currentData() == "vv/vh"
        except Exception:
            return False

    def _update_irf_label(self) -> None:
        """Update the IRF source label based on the currently selected dataset."""
        try:
            ds = getattr(self, "_irf_dataset", None)
        except Exception:
            ds = None

        if ds is None:
            text = "IRF: Gaussian (no dataset selected)"
        else:
            try:
                name = getattr(ds, "name", None) or getattr(ds, "filename", None)
            except Exception:
                name = None
            if not name:
                name = "IRF dataset"
            text = f"IRF: {name}"

        try:
            self.label_irf_source.setText(text)
        except Exception:
            pass

    def _on_irf_button_clicked(self) -> None:
        """Show the IRF selector window when the user clicks the select button."""
        try:
            self.irf_selector.show()
        except Exception:
            pass

    def _on_irf_unload_clicked(self) -> None:
        """Unload the currently selected IRF and revert to Gaussian mode."""
        try:
            self._irf_dataset = None
        except Exception:
            pass
        self._update_irf_label()

    def _on_irf_selection_changed(self):
        """Callback used by the hidden IRF selector when the selection changes."""
        ds = None
        try:
            ds = self.irf_selector.selected_dataset
        except Exception:
            ds = None

        try:
            self._irf_dataset = ds
        except Exception:
            pass

        self._update_irf_label()

    def _build_irf(self, time_axis: np.ndarray) -> np.ndarray:
        """Return an IRF on the given time axis.

        Preference order:
        1. Use the currently selected TCSPC dataset in the selector.
        2. Fall back to a Gaussian IRF defined by mean/std spin boxes.

        The resolution itself lives in the core simulator so the reader-level
        ``read()`` path sees the same response.
        """
        from chisurf.core.experiments.tcspc.simulator import resolve_irf as _resolve_irf

        try:
            ds = getattr(self, "_irf_dataset", None)
        except Exception:
            ds = None

        try:
            mean = float(self.doubleSpinBox_irf_mean.value())
        except Exception:
            mean = 5.0
        try:
            sigma = float(self.doubleSpinBox_irf_sigma.value())
        except Exception:
            sigma = 0.2

        return _resolve_irf(time_axis, ds, mean=mean, sigma=sigma)

    def _simulate_decay(self) -> tuple[np.ndarray | None, np.ndarray | None]:
        """Compute simulated TCSPC decay for current parameters and IRF.

        The decay is generated by the core simulator
        (:func:`chisurf.core.experiments.tcspc.simulator.simulate_decay`) — the
        same generator the reader's ``read()`` path uses — so the **Simulate**
        and **+ Data** buttons agree. The IRF used for the simulation is stored
        (scaled) for plotting.
        """
        import numpy as _np

        from chisurf.core.experiments.tcspc.simulator import simulate_decay as _simulate

        lifetime_spectrum = self._parse_lifetime_spectrum()
        if lifetime_spectrum.size == 0:
            return None, None

        try:
            n_tac = int(self.spinBox.value())
        except Exception:
            n_tac = 4096
        try:
            dt = float(self.doubleSpinBox.value())
        except Exception:
            dt = 0.0141
        try:
            p0 = float(self.spinBox_2.value())
        except Exception:
            p0 = 0.0

        time_axis = _np.arange(int(max(1, n_tac)), dtype=float) * dt
        irf = self._build_irf(time_axis)

        if self._is_vvvh_mode():
            # Polarized simulation: the VV/VH pair through the same forward
            # model the fit uses (g, l1, l2 and the rotation spectrum).
            from chisurf.core.experiments.tcspc.simulator import (
                simulate_decay_channels as _simulate_channels,
            )

            try:
                g = float(self.doubleSpinBox_g_factor.value())
            except Exception:
                g = 1.0
            try:
                l1 = float(self.doubleSpinBox_l1.value())
            except Exception:
                l1 = 0.0
            try:
                l2 = float(self.doubleSpinBox_l2.value())
            except Exception:
                l2 = 0.0

            _, vv, vh = _simulate_channels(
                lifetime_spectrum,
                self._parse_rotation_spectrum(),
                n_tac=n_tac,
                dt=dt,
                p0=p0,
                g_factor=g,
                l1=l1,
                l2=l2,
                irf=irf,
            )
            self._sim_t = time_axis
            self._sim_vv, self._sim_vh = vv, vh
            self._sim_y = None
            self._sim_irf = self._scale_irf_for_plot(irf, vv)
            return time_axis, vv

        time_axis, decay_counts = _simulate(
            lifetime_spectrum,
            n_tac=n_tac,
            dt=dt,
            p0=p0,
            irf=irf,
        )
        self._sim_vv, self._sim_vh = None, None
        self._sim_irf = self._scale_irf_for_plot(irf, decay_counts)

        return time_axis, decay_counts

    def _scale_irf_for_plot(self, irf: np.ndarray, reference: np.ndarray) -> np.ndarray:
        """Return the IRF scaled to the reference trace's amplitude for plotting."""
        import numpy as _np

        irf_plot = _np.asarray(irf, dtype=float)
        try:
            max_irf = float(_np.max(irf_plot))
        except Exception:
            max_irf = 0.0
        try:
            max_ref = float(_np.max(reference))
        except Exception:
            max_ref = 0.0
        if max_irf > 0.0 and max_ref > 0.0:
            irf_plot = irf_plot * (max_ref / max_irf)
        return irf_plot

    def _refresh_anisotropy_plot(self) -> None:
        """Draw the ideal r(t) of the rotation spectrum on the aniso plot."""
        try:
            t = getattr(self, "_sim_t", None)
            rot = self._parse_rotation_spectrum()
            if t is None or np.size(t) == 0 or rot.size == 0:
                self.anisotropy_plot.clear()
                return
            from chisurf.core.fluorescence.anisotropy.decay import anisotropy_rt

            r = anisotropy_rt(np.asarray(t, dtype=float), rot)
            self.anisotropy_plot.clear()
            self.anisotropy_plot.line(t, r, pen="w")
        except Exception:
            pass

    def _refresh_simulation_plot(self) -> None:
        t = getattr(self, "_sim_t", None)
        y = getattr(self, "_sim_y", None)
        irf = getattr(self, "_sim_irf", None)
        vv = getattr(self, "_sim_vv", None)
        vh = getattr(self, "_sim_vh", None)
        if t is None or (y is None and (vv is None or vh is None)):
            return
        if np.size(t) == 0 or (y is not None and np.size(y) == 0):
            return
        try:
            self.simulation_plot.clear()
            if y is not None:
                # Magic-angle decay
                self.simulation_plot.line(t, y, pen="y")
            else:
                # Polarized pair: parallel and perpendicular channels
                y = vv
                self.simulation_plot.line(t, vv, pen="m")
                self.simulation_plot.line(t, vh, pen="b")
            # IRF overlay (if available and matching length)
            if irf is not None and np.size(irf) == np.size(t):
                self.simulation_plot.line(t, irf, pen="r")
            try:
                self.simulation_plot.set_log(y=True)
            except Exception:
                pass

            # Enforce a minimum visible y-value of 0.1 on the log-scaled axis
            try:
                y_main = np.asarray(y, dtype=float)
                if irf is not None and np.size(irf) == np.size(y_main):
                    y_irf = np.asarray(irf, dtype=float)
                    y_all = np.maximum(y_main, y_irf)
                else:
                    y_all = y_main
                y_pos = y_all[y_all > 0]
                if y_pos.size:
                    y_max = float(y_pos.max())
                    y_min = 0.1
                    if y_max <= y_min:
                        y_max = y_min * 10.0
                    # Data units, not exponents: chiplot's set_ylim takes the
                    # values on every axis and the backend converts. Passing
                    # log10 here worked only because pyqtgraph's view happens
                    # to hold exponents in log mode, and drew a decay spanning
                    # 0.1 to 4 counts on the native renderer.
                    self.simulation_plot.set_ylim(y_min, y_max)
            except Exception:
                pass
        except Exception:
            pass

    def _on_simulate_clicked(self) -> None:
        t, y = self._simulate_decay()
        if t is None or y is None:
            return
        self._sim_t = t
        if not self._is_vvvh_mode():
            # In VV/VH mode ``_simulate_decay`` already stored the pair and
            # keeps ``_sim_y`` empty; the returned value is the VV channel.
            self._sim_y = y
        self._refresh_simulation_plot()
        self._refresh_anisotropy_plot()

    def _on_add_clicked(self) -> None:
        """Add the last simulated decay as a dataset to imported_datasets.

        The dataset is wrapped into an ExperimentDataCurveGroup with
        experiment, setup and data_reader metadata so that it behaves like
        TCSPC datasets loaded via CSV/TTTR readers.
        """
        import numpy as _np

        from chisurf.macros import core_data as _core_data

        t = getattr(self, "_sim_t", None)
        y = getattr(self, "_sim_y", None)
        vv = getattr(self, "_sim_vv", None)
        vh = getattr(self, "_sim_vh", None)
        if (
            t is None
            or _np.size(t) == 0
            or ((y is None or _np.size(y) == 0) and (vv is None or vh is None))
        ):
            # If nothing simulated yet, try to simulate now
            t, y = self._simulate_decay()
            if t is None:
                return
            y = getattr(self, "_sim_y", None)
            vv = getattr(self, "_sim_vv", None)
            vh = getattr(self, "_sim_vh", None)
            if (y is None or _np.size(y) == 0) and (vv is None or vh is None):
                return
            self._sim_t = t

        try:
            name = str(self.lineEdit.text()) or "TCSPC-Simulated"
        except Exception:
            name = "TCSPC-Simulated"

        # Resolve experiment, setup and reader from the global ChiSurf state
        gui = getattr(cs, "cs", None)

        try:
            experiment = getattr(gui, "current_experiment", None) if gui is not None else None
        except Exception:
            experiment = None
        try:
            setup = getattr(gui, "current_setup", None) if gui is not None else None
        except Exception:
            setup = None
        try:
            experiment_reader = (
                getattr(gui, "current_experiment_reader", None) if gui is not None else None
            )
        except Exception:
            experiment_reader = None

        try:
            from chisurf.core.fluorescence import tcspc as _tcspc_mod

            if vv is not None and vh is not None:
                ey_vv = _tcspc_mod.counting_noise(vv)
                ey_vh = _tcspc_mod.counting_noise(vh)
            else:
                ey = _tcspc_mod.counting_noise(y)
        except Exception:
            ey = ey_vv = ey_vh = None

        if vv is not None and vh is not None:
            # Polarized pair: two stacked curves in one group — the same
            # structure a VV/VH file load produces, so *Add fit* opens a fit
            # group with vv/vh polarizations by position. The calibration
            # (g/l1/l2) rides on the reader (this setup), which is where
            # add_fit looks first.
            try:
                pol_meta = {
                    "polarization": "vv/vh",
                    "g_factor": float(self.doubleSpinBox_g_factor.value()),
                    "l1": float(self.doubleSpinBox_l1.value()),
                    "l2": float(self.doubleSpinBox_l2.value()),
                }
            except Exception:
                pol_meta = {"polarization": "vv/vh"}

            curves = []
            for suffix, yy, eyy in (("VV", vv, ey_vv), ("VH", vh, ey_vh)):
                curve = cs.core.data.DataCurve(
                    x=_np.asarray(t, dtype=float),
                    y=_np.asarray(yy, dtype=float),
                    ey=eyy,
                    name=f"{name} {suffix}",
                    experiment=experiment,
                    data_reader=experiment_reader,
                    setup=setup,
                )
                curve.meta_data = dict(pol_meta)
                curves.append(curve)

            try:
                dataset_group = cs.core.data.ExperimentDataCurveGroup(curves)
            except Exception:
                dataset_group = None

            if dataset_group is not None and gui is not None:
                try:
                    cs.imported_datasets.append(dataset_group)
                    cs.gui.run_on_gui_thread(gui.update)
                    return
                except Exception:
                    pass
            _core_data.add_dataset(experiment_reader=experiment_reader, dataset=curves[0])
            return

        # Create an experimental curve with proper metadata so selectors and
        # fits see it like any other TCSPC dataset.
        data_set = cs.core.data.DataCurve(
            x=_np.asarray(t, dtype=float),
            y=_np.asarray(y, dtype=float),
            ey=ey,
            name=name,
            experiment=experiment,
            data_reader=experiment_reader,
            setup=setup,
        )

        # Wrap into an ExperimentDataCurveGroup to mirror grouped imports.
        try:
            dataset_group = cs.core.data.ExperimentDataCurveGroup([data_set])
        except Exception:
            dataset_group = None

        if dataset_group is not None and gui is not None:
            try:
                cs.imported_datasets.append(dataset_group)
                cs.gui.run_on_gui_thread(gui.update)
                return
            except Exception:
                pass

        # Fallback to the generic add_dataset helper if grouping fails
        _core_data.add_dataset(experiment_reader=experiment_reader, dataset=data_set)
