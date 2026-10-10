"""Grab functions for guides 56, 57, 65.

The guide-55 flow grab is left out on purpose: the flow demo currently draws
no arrows (known-issues), and re-grabbing would overwrite the figure that
shows the intended result.

Uses FIG and _pump from common.py. Each
function saves into FIG. Run each in its own subprocess with a timeout: the
acquisition and main-window grabs start threads and servers.
"""
import pathlib, tempfile, time

from common import FIG, _pump  # noqa: F401

def _grab_56_fcs_saturation():
    from chisurf.plugins.calculator.fcs_saturation_calc.gui.tool import SaturationCalculatorTool
    tool = SaturationCalculatorTool()
    tool.resize(1900, 1000); tool.show(); _pump(0.5)
    tool.power_mW = 2.0
    tool._on_compute(); _pump(2)
    tool.form.sync_fields(); _pump(1)
    import re
    print("info", re.sub(r"<[^>]+>", " ", tool._info_summary)[:900], flush=True)
    print("power", tool.power_mW, "wl", tool.wavelength_nm, flush=True)
    tool.grab().save(str(FIG / "fcs_saturation_tool.png"))
    return tool


def _grab_57_mfd_fit():
    import chisurf as cs
    import chisurf.core.settings as _cfg
    _cfg.cs_settings.setdefault("mmfdb", {})["cmd_port"] = 8977
    _cfg.cs_settings["mmfdb"]["pub_port"] = 8978
    _cfg.cs_settings["mmfdb"]["last_port"] = 8977
    _cfg.cs_settings["mmfdb"].setdefault("client", {}).update(cmd_port=8977, pub_port=8978)
    from chisurf.core.fluorescence.burst.simulate import rate_matrix_for, simulate_smfret
    folder = pathlib.Path(tempfile.gettempdir()) / "chisurf-mfd-demo"
    if not (folder / "bi4_bur").exists() and not any(folder.glob("**/*.bur")):
        simulated = simulate_smfret(
            alex=False, polarized=True,
            efficiencies=(0.786, 0.152), donor_only=0.15,
            n_photons=360_000, irf_centre=1.2, irf_width=0.09,
            rate_matrix=rate_matrix_for("intermediate", mean_duration=2e-3),
        )
        folder = pathlib.Path(simulated.write_folder(str(folder)))
    print("folder", folder, list(folder.iterdir())[:5])
    import chisurf.gui
    app = chisurf.gui.get_app()
    gui = cs.cs
    gui.resize(1700, 1000); gui.show(); _pump(1)
    gui.comboBox_experimentSelect.setCurrentIndex(gui.comboBox_experimentSelect.findText("MFD"))
    gui._refresh_experiment_ui()
    gui.comboBox_setupSelect.setCurrentIndex(gui.comboBox_setupSelect.findText("MFD (burst folder)"))
    gui._refresh_setup_ui()
    burs = sorted(folder.glob("**/*.bur"))
    target = burs[0].parent if burs else folder
    print("loading", target)
    cs.core.actions.dispatch(name="dataset.add", payload={"filename": str(target), "experiment_reader": None})
    _pump(1)
    print("datasets", len(cs.imported_datasets))
    idx = len(cs.imported_datasets) - 1
    cs.core.actions.dispatch(name="fit.add", payload={"dataset_indices": [idx], "model_name": "MFD 2D"})
    print("fits", len(cs.fits), flush=True)
    fit = cs.fits[-1]
    print("fit", type(fit).__name__, type(fit.model).__name__, flush=True)
    _pump(2)
    from chisurf.gui.widgets.fitting.widgets import FittingControllerWidget
    sw = gui.mdiarea.subWindowList()[-1]
    sw.showMaximized(); _pump(0.5)
    ctrls = gui.findChildren(FittingControllerWidget)
    print("ctrls", len(ctrls), flush=True)
    t0 = time.time()
    fit.model.update()
    print("model update s", time.time() - t0, flush=True)
    free = [p.name for p in fit.model.parameters if not getattr(p, "fixed", True)] if hasattr(fit.model, "parameters") else []
    print("free", free, flush=True)
    _pump(1)
    try:
        print("summary", getattr(fit.model, "_last_summary", None), flush=True)
    except Exception as e:
        print(e)
    for dock in ("dockWidgetAnalysis",):
        d = getattr(gui, dock, None)
        if d is not None:
            d.show(); d.raise_()
    _pump(1)
    gui.grab().save(str(FIG / "57_mfd_fit_window.png")); print("saved", flush=True)
    w = sw.widget() if hasattr(sw, "widget") and sw.widget() is not None else sw
    tabs = getattr(sw, "plot_tab_widget", None) or getattr(w, "plot_tab_widget", None)
    names = [tabs.tabText(i) for i in range(tabs.count())] if tabs is not None else []
    print("tabs", names, flush=True)
    if "MFD marginals" in names:
        i = names.index("MFD marginals")
        tabs.setCurrentIndex(i); _pump(0.5)
        try:
            sw.ensure_plot_created(i).update_all()
        except Exception as e:
            print("update_all", e, flush=True)
        _pump(1)
        gui.grab().save(str(FIG / "57_mfd_marginals.png")); print("saved2", flush=True)
    return gui


def _grab_65_acquisition_settings():
    from chisurf.plugins.core.acq.gui.settings_panel import AcquisitionSettingsWidget
    w = AcquisitionSettingsWidget()
    w.resize(760, 900); w.show(); _pump(1.0)
    dlg = w._device_dialog
    print(type(dlg), [a for a in dir(dlg) if 'model' in a.lower()][:10])
    try:
        dlg.model.excitation_mode = "Pulsed"
        dlg.form.sync_fields(); dlg.form.refresh_plots()
    except Exception as e:
        print("set mode failed", e)
    _pump(0.5)
    w.grab().save(str(FIG / "65_acquisition_settings.png"))
    return w

