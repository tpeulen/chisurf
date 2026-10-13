import numpy as np
from qtpy import QtWidgets

from chisurf.gui import chiplot as cp
from chisurf.gui import dialogs
from chisurf.gui.widgets.models.tcspc.forster_helpers import open_forster_calculator


def _plotting_available() -> bool:
    """Return whether a chiplot rendering backend can be instantiated.

    Returns
    -------
    bool
        ``True`` if the active backend (and its underlying renderer) imports
        cleanly, ``False`` otherwise — used to degrade gracefully to a warning.
    """
    try:
        cp.get_backend()
        return True
    except Exception:  # pragma: no cover - renderer may be missing in headless envs
        return False


def setup_kappa2_controls(
    owner: QtWidgets.QWidget,
    parent_layout: QtWidgets.QLayout,
    fret_model=None,
) -> None:
    """Attach shared κ² mode controls to *owner* using *parent_layout*.

    This creates Dynamic/Static radio buttons and two tool buttons
    (distribution plot and experimental κ²), wires them to the shared
    helper functions, and stores references on *owner* for later use.

    Parameters
    ----------
    owner : QtWidgets.QWidget
        Widget that parents the controls and the dialogs they open.
    parent_layout : QtWidgets.QLayout
        Layout the control row is added to.
    fret_model : optional
        The FRET model the controls read and write. Defaults to `owner`, which
        is correct for a legacy widget that *is* its own model. A generated
        editor must pass the model explicitly, because there the owner is the
        section widget and holds no parameters of its own.
    """
    model = fret_model if fret_model is not None else owner

    mode_layout = QtWidgets.QHBoxLayout()
    dyn_radio = QtWidgets.QRadioButton("dynamic κ²")
    stat_radio = QtWidgets.QRadioButton("static κ²")
    mode_layout.addWidget(dyn_radio)
    mode_layout.addWidget(stat_radio)

    mode_layout.addStretch(1)

    # Fast optimization checkbox for static kappa2 convolution
    fast_checkbox = QtWidgets.QCheckBox("Fast")
    fast_checkbox.setChecked(True)
    fast_checkbox.setToolTip(
        "Use fast loop-based convolution for static κ² distributions.\n"
        "Provides speedup for large κ² distributions by looping over\n"
        "ratio values and accumulating shifted distance histograms.\n"
        "Disable for exact outer product."
    )
    mode_layout.addWidget(fast_checkbox)

    show_btn = QtWidgets.QToolButton()
    show_btn.setText("show κ²")
    mode_layout.addWidget(show_btn)

    exp_btn = QtWidgets.QToolButton()
    exp_btn.setText("compute κ²")
    mode_layout.addWidget(exp_btn)

    calc_r0_btn = QtWidgets.QToolButton()
    calc_r0_btn.setText("calc R0")
    calc_r0_btn.setToolTip("Open the Förster radius calculator to compute R₀ from MMFDB spectra")
    mode_layout.addWidget(calc_r0_btn)
    calc_r0_btn.clicked.connect(lambda: open_forster_calculator(model))

    parent_layout.addLayout(mode_layout)

    group = QtWidgets.QButtonGroup(owner)
    group.addButton(dyn_radio)
    group.addButton(stat_radio)
    group.setExclusive(True)

    orientation_param = getattr(model, "orientation_parameter", None)
    current_mode = (
        getattr(orientation_param, "mode", "fast") if orientation_param is not None else "fast"
    )
    if current_mode == "slow":
        stat_radio.setChecked(True)
    else:
        dyn_radio.setChecked(True)

    # TODO: needs docstring
    def on_mode_changed() -> None:
        """Handle dynamic/static radio button change."""
        op = getattr(model, "orientation_parameter", None)
        if op is None:
            return
        op.mode = "slow" if stat_radio.isChecked() else "fast"
        try:
            model.update()
        except Exception:
            pass

    dyn_radio.toggled.connect(on_mode_changed)
    stat_radio.toggled.connect(on_mode_changed)

    def on_fft_changed() -> None:
        """Trigger model update when FFT checkbox state changes."""
        try:
            model.update()
        except Exception:
            pass

    fast_checkbox.stateChanged.connect(on_fft_changed)

    # TODO: needs docstring
    def on_show_combined() -> None:
        """Handle show kappa2 distribution button."""
        show_rapp_rda_distribution_plot(
            parent=owner,
            orientation_parameter=getattr(model, "orientation_parameter", None),
            fret_model=model,
        )

    # TODO: needs docstring
    def on_open_experimental() -> None:
        """Handle experimental kappa2 button."""
        open_experimental_k2_dialog(parent=owner, fret_model=model)

    show_btn.clicked.connect(on_show_combined)
    exp_btn.clicked.connect(on_open_experimental)

    # Expose on owner for potential introspection / testing
    owner._kappa2_dynamic_radio = dyn_radio
    owner._kappa2_static_radio = stat_radio
    owner._kappa2_fft_checkbox = fast_checkbox
    owner._kappa2_show_distribution_button = show_btn
    owner._kappa2_experimental_button = exp_btn
    owner._forster_calculator_button = calc_r0_btn
    owner._kappa2_mode_group = group


def _extract_kappa2_pairs(orientation_parameter, fret_parameters):
    """Return the ``(amplitude, k2)`` pairs the model averages over, and its mode.

    One rule for both editors: :func:`chisurf.core.models.tcspc.kappa2_controls.used_kappa2_pairs`
    (static: the held distribution, isotropic when none is held; dynamic: the scalar k2).
    """
    from chisurf.core.models.tcspc.kappa2_controls import DYNAMIC_KAPPA2, used_kappa2_pairs

    if orientation_parameter is not None:
        mode = getattr(orientation_parameter, "mode", "fast")
    else:
        mode = getattr(fret_parameters, "mode", "fast") if fret_parameters is not None else "fast"
    try:
        scalar = float(getattr(fret_parameters, "kappa2", DYNAMIC_KAPPA2))
    except (TypeError, ValueError):
        scalar = DYNAMIC_KAPPA2
    return used_kappa2_pairs(orientation_parameter, scalar), mode


def show_kappa2_distribution_plot(
    parent: QtWidgets.QWidget | None = None,
    orientation_parameter=None,
    fret_parameters=None,
) -> None:
    """Show a simple dialog with the current orientation factor distribution.

    This works both for the static distribution (slow) and for the
    dynamic scalar case (fast, shown as a single spike at k2).
    """
    if not _plotting_available():
        dialogs.warning(
            parent,
            "Orientation factor distribution",
            "Plotting backend is not available, cannot plot k2 distribution.",
        )
        return

    pairs, mode = _extract_kappa2_pairs(orientation_parameter, fret_parameters)

    # The distribution the model actually averages over -- never a second guess at it.
    static_pairs = list(pairs)

    if not static_pairs:
        dialogs.information(
            parent,
            "Orientation factor distribution",
            "No orientation factor distribution is available.",
        )
        return

    try:
        dynamic_k2 = (
            float(getattr(fret_parameters, "kappa2", 0.666))
            if fret_parameters is not None
            else 0.666
        )
    except Exception:
        dynamic_k2 = 0.666

    amps = np.asarray([a for (a, _) in static_pairs], dtype=float)
    k2_vals = np.asarray([k for (_, k) in static_pairs], dtype=float)
    finite = np.isfinite(amps) & np.isfinite(k2_vals)
    amps = amps[finite]
    k2_vals = k2_vals[finite]
    if amps.size == 0:
        dialogs.information(
            parent,
            "Orientation factor distribution",
            "No valid orientation factor distribution is available.",
        )
        return

    total = float(np.sum(amps))
    if total > 0:
        amps = amps / total
    static_mean = float(np.sum(amps * k2_vals))

    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Orientation factor distribution (k2)")
    layout = QtWidgets.QVBoxLayout(dialog)

    mode_label = "slow" if mode == "slow" else "fast"
    info_label = QtWidgets.QLabel(
        f"Current orientation mode: {mode_label} | "
        f"dynamic k2={dynamic_k2:.3f} | static avg={static_mean:.3f}"
    )
    layout.addWidget(info_label)

    # Sort by k2 value to have a nice monotonic x-axis
    order = np.argsort(k2_vals)
    k2_vals_sorted = k2_vals[order]
    weights_sorted = amps[order]

    plot_widget = cp.Panel()
    plot_widget.grid(x=True, y=True, alpha=0.3)
    plot_widget.set_labels(bottom="k2", left="Weight")
    plot_widget.legend()
    plot_widget.line(
        k2_vals_sorted,
        weights_sorted,
        width=2,
        symbol="o",
        symbol_size=6,
        name="static distribution",
    )

    y_max = float(np.max(weights_sorted)) if weights_sorted.size else 1.0
    y_line = y_max * 1.05
    plot_widget.line(
        [dynamic_k2, dynamic_k2],
        [0.0, y_line],
        pen=(80, 160, 255),
        width=2,
        name="dynamic (k2)",
    )
    plot_widget.line(
        [static_mean, static_mean],
        [0.0, y_line],
        pen=(255, 160, 80),
        width=2,
        style="dash",
        name="static avg",
    )

    try:
        plot_widget.text("dynamic", (dynamic_k2, y_line), color=(80, 160, 255), anchor=(0.5, 1.0))
    except Exception:
        pass

    try:
        plot_widget.text(
            "static avg", (static_mean, y_line), color=(255, 160, 80), anchor=(0.5, 1.0)
        )
    except Exception:
        pass

    layout.addWidget(cp.host(plot_widget, dialog))

    button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
    button_box.accepted.connect(dialog.accept)
    layout.addWidget(button_box)

    dialog.resize(500, 400)
    dialog.exec_()


def show_rapp_rda_distribution_plot(
    parent: QtWidgets.QWidget | None = None,
    orientation_parameter=None,
    fret_model=None,
) -> None:
    """Show the κ² distribution transformed to R_app/R_DA ratio scale.

    This displays the distribution used for FFT convolution:
    R_app/R_DA = (κ²/⟨κ²⟩)^(1/6)
    """
    if not _plotting_available():
        dialogs.warning(
            parent,
            "R_app/R_DA distribution",
            "Plotting backend is not available, cannot plot distribution.",
        )
        return

    # Get fret_parameters from fret_model if available
    fret_parameters = (
        getattr(fret_model, "fret_parameters", None) if fret_model is not None else None
    )
    pairs, mode = _extract_kappa2_pairs(orientation_parameter, fret_parameters)

    # The distribution the model actually averages over -- never a second guess at it.
    static_pairs = list(pairs)

    if not static_pairs:
        dialogs.information(
            parent,
            "R_app/R_DA distribution",
            "No orientation factor distribution is available.",
        )
        return

    amps = np.asarray([a for (a, _) in static_pairs], dtype=float)
    k2_vals = np.asarray([k for (_, k) in static_pairs], dtype=float)
    finite = np.isfinite(amps) & np.isfinite(k2_vals)
    amps = amps[finite]
    k2_vals = k2_vals[finite]

    if amps.size == 0:
        dialogs.information(
            parent,
            "R_app/R_DA distribution",
            "No valid orientation factor distribution is available.",
        )
        return

    # Use shared transformation function from chisurf.core.fluorescence.general
    from chisurf.core.fluorescence.general import kappa2_to_distance_ratio

    r_ratio, weights, k2_mean = kappa2_to_distance_ratio(amps, k2_vals, n_bins=256)

    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("κ² & Rₐₚₚ/Rᴅᴀ distributions")
    layout = QtWidgets.QVBoxLayout(dialog)

    info_label = QtWidgets.QLabel(
        f"Transformation: Rₐₚₚ/Rᴅᴀ = (⟨κ²⟩/κ²)^(1/6) | ⟨κ²⟩ = {k2_mean:.3f}"
    )
    layout.addWidget(info_label)

    # First plot: κ² distribution
    plot_k2 = cp.Panel()
    plot_k2.grid(x=True, y=True, alpha=0.3)
    plot_k2.set_labels(bottom="κ²", left="Probability")
    plot_k2.legend()
    plot_k2.line(
        k2_vals,
        amps / np.sum(amps) if np.sum(amps) > 0 else amps,
        pen=(255, 100, 100),
        width=2,
        symbol="o",
        symbol_size=5,
        name="ρ(κ²)",
    )
    # Mark mean κ²
    k2_max_y = float(np.max(amps / np.sum(amps))) if np.sum(amps) > 0 else 1.0
    plot_k2.line(
        [k2_mean, k2_mean],
        [0.0, k2_max_y * 1.05],
        pen=(255, 160, 80),
        width=2,
        style="dash",
        name=f"⟨κ²⟩ = {k2_mean:.3f}",
    )
    layout.addWidget(cp.host(plot_k2, dialog))

    # Second plot: R_app/R_DA ratio distribution
    plot_widget = cp.Panel()
    plot_widget.grid(x=True, y=True, alpha=0.3)
    plot_widget.set_labels(bottom="Rₐₚₚ/Rᴅᴀ", left="Probability Density")
    plot_widget.legend()
    plot_widget.line(
        r_ratio,
        weights,
        pen=(80, 160, 255),
        width=2,
        name="ρ(Rₐₚₚ/Rᴅᴀ)",
    )

    # Mark the mean ratio (should be 1.0 by definition)
    y_max = float(np.max(weights)) if weights.size else 1.0
    y_line = y_max * 1.05
    plot_widget.line(
        [1.0, 1.0],
        [0.0, y_line],
        pen=(255, 160, 80),
        width=2,
        style="dash",
        name="mean (1.0)",
    )

    try:
        plot_widget.text("(2/3)^(1/6)", (1.0, y_line), color=(255, 160, 80), anchor=(0.5, 1.0))
    except Exception:
        pass

    layout.addWidget(cp.host(plot_widget, dialog))

    # Second plot: R_DA and R_app distributions after convolution
    # Get distance distribution from fret_model
    distance_dist = None
    if fret_model is not None:
        # Try to get distance distribution directly from the model
        try:
            distance_dist = getattr(fret_model, "distance_distribution", None)
        except Exception:
            pass

    if distance_dist is not None:
        try:
            # Extract R_DA distribution
            dist_array = np.asarray(distance_dist, dtype=float)
            if dist_array.ndim == 3 and dist_array.shape[0] > 0:
                # Shape is (n_dist, 2, n_points) - extract first distribution
                amp_r = dist_array[0, 0, :]
                r_da = dist_array[0, 1, :]

                # Filter valid points
                valid = (amp_r > 0) & np.isfinite(r_da) & (r_da > 0)
                amp_r = amp_r[valid]
                r_da = r_da[valid]

                if len(r_da) > 0:
                    # Get Fast setting from UI checkbox
                    use_fast = True
                    if fret_model is not None:
                        fast_checkbox = getattr(fret_model, "_kappa2_fft_checkbox", None)
                        if fast_checkbox is not None:
                            use_fast = fast_checkbox.isChecked()

                    # Compute R_app distribution via convolution using shared function
                    from chisurf.core.fluorescence.general import convolve_distance_with_k2_ratio

                    r_app_centers, r_app_hist = convolve_distance_with_k2_ratio(
                        r_da, amp_r, r_ratio, weights, n_bins=256, use_fast=use_fast
                    )

                    # Normalize both distributions to max=1.0 for comparison
                    max_amp_r = np.max(amp_r)
                    max_r_app = np.max(r_app_hist)

                    if max_amp_r > 0:
                        amp_r_norm = amp_r / max_amp_r
                    else:
                        amp_r_norm = amp_r

                    if max_r_app > 0:
                        r_app_hist_norm = r_app_hist / max_r_app
                    else:
                        r_app_hist_norm = r_app_hist

                    # Create second plot
                    plot_widget2 = cp.Panel()
                    plot_widget2.grid(x=True, y=True, alpha=0.3)
                    plot_widget2.set_labels(bottom="Distance (Å)", left="Normalized Intensity")
                    plot_widget2.legend()

                    # Plot R_DA
                    plot_widget2.line(
                        r_da,
                        amp_r_norm,
                        pen=(80, 255, 160),
                        width=2,
                        symbol="o",
                        symbol_size=4,
                        name="ρ(Rᴅᴀ)",
                    )

                    # Plot R_app
                    plot_widget2.line(
                        r_app_centers,
                        r_app_hist_norm,
                        pen=(255, 80, 160),
                        width=2,
                        name="ρ(Rₐₚₚ)",
                    )

                    layout.addWidget(cp.host(plot_widget2, dialog))
        except Exception:
            # Silently skip if distance distribution cannot be processed
            pass

    button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
    button_box.accepted.connect(dialog.accept)
    layout.addWidget(button_box)

    dialog.resize(500, 400)
    dialog.exec_()


def open_experimental_k2_dialog(
    parent: QtWidgets.QWidget | None = None,
    fret_model=None,
) -> None:
    """Open the Kappa2Dist plugin dialog and apply its distribution to a FRET model.

    Fast mode: use mean k2 from the distribution as scalar kappa2.
    Slow mode: use full k2 distribution as orientation spectrum.
    """
    try:
        from emtk.qt_host import ControlHost

        from chisurf.plugins.calculator.kappa2_dist.gui.app import WINDOW_BG, make_app
    except Exception:
        dialogs.error(
            parent,
            "Experimental k2",
            "Kappa2 Distribution plugin is not available.",
        )
        return

    if fret_model is None:
        dialogs.information(
            parent,
            "Experimental k2",
            "No FRET model is available to apply the kappa2 distribution.",
        )
        return

    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Experimental k2 (orientation factor distribution)")
    layout = QtWidgets.QVBoxLayout(dialog)

    # Start from the current scalar k2; the emtk app is the calculator, Qt only hosts it.
    try:
        k2_start = float(getattr(fret_model.fret_parameters, "kappa2", 0.666))
    except Exception:
        k2_start = 0.666

    app = make_app(kappa2=k2_start)
    host = ControlHost(app, background=WINDOW_BG[:3])
    layout.addWidget(host)

    button_box = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
    )
    layout.addWidget(button_box)
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)

    if dialog.exec_() != QtWidgets.QDialog.Accepted:
        return

    # Extract distribution and mean from the calculator (computed for the inputs as they stand).
    try:
        app.compute_now()
        model = app.tool._model
        k2scale_raw = np.asarray(model._k2scale, dtype=float)
        k2hist = np.asarray(model._k2hist, dtype=float)
        k2_mean = float(model.k2_mean)
    except Exception:
        k2scale_raw = np.array([], dtype=float)
        k2hist = np.array([], dtype=float)
        k2_mean = np.nan

    from chisurf.core.models.tcspc.kappa2_controls import apply_kappa2_distribution

    try:
        apply_kappa2_distribution(fret_model, k2scale_raw, k2hist, k2_mean)
    except ValueError as error:
        dialogs.warning(parent, "Experimental k2", str(error))
