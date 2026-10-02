"""Populated captures of the Qt tool of an imaging pixel plugin on the shared synthetic photon stream.

Usage: capture_qt_pixel.py <plugin_id> <out_dir>   (writes before_populated_*.png, before_tab_*.png, qt_values.json)
Everything on temporary settings and a temporary HOME; no network.
"""
def main():
    import json, os, pathlib, sys, tempfile, time

    tmp = pathlib.Path(tempfile.mkdtemp())
    os.environ.update(CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"), HOME=str(tmp / "home"),
                      QT_QPA_PLATFORM="offscreen")
    (tmp / "home").mkdir()
    import numpy as np
    from qtpy import QtCore, QtWidgets

    HERE = pathlib.Path(__file__).resolve().parent
    sys.path.insert(0, str(HERE))
    import imaging_pixel_data as data  # noqa: E402

    pid = sys.argv[1]
    out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    TOOLS = {
        "img_pixel_intensity": ("img_pixel_intensity.gui.tool", "ImgPixelIntensityTool"),
        "img_pixel_micro_time": ("img_pixel_micro_time.gui.tool", "ImgPixelMicroTimeTool"),
        "img_pixel_phasor": ("img_pixel_phasor.gui.tool", "ImgPixelPhasorTool"),
        "img_pixel_nb": ("img_pixel_nb.gui.tool", "ImgPixelNBTool"),
        "img_pixel_mle": ("img_pixel_mle.gui.tool", "ImgPixelMleTool"),
        "img_coloc": ("img_coloc.gui.tool", "ImgColocTool"),
    }
    import importlib
    mod = importlib.import_module("chisurf.plugins.microscopy." + TOOLS[pid][0])
    w = getattr(mod, TOOLS[pid][1])()
    w.resize(1200, 800); w.show()
    m = w.model


    def settle(n=40):
        for _ in range(n):
            app.processEvents()


    def grab(name):
        settle(); w.grab().save(str(out / f"{name}.png"))


    def tabs():
        return [(bar, i, bar.tabText(i)) for bar in w.findChildren(QtWidgets.QTabBar) for i in range(bar.count())]


    def grab_tabs(prefix="before_tab_"):
        for bar, i, text in tabs():
            bar.setCurrentIndex(i); settle()
            grab(prefix + "".join(c if c.isalnum() else "_" for c in text).strip("_"))
        for bar, i, text in tabs()[:1]:
            bar.setCurrentIndex(0)


    def stat(a):
        a = None if a is None else np.asarray(a, float)
        return None if a is None else {"shape": list(a.shape), "sum": float(np.nansum(a)), "mean": float(np.nanmean(a)), "min": float(np.nanmin(a)), "max": float(np.nanmax(a)),
                                      "row0": [float(v) for v in a.reshape(-1, a.shape[-1])[0]]}


    vals = {"tabs": [t for _, _, t in tabs()]}
    ptu = data.flim_ptu(tmp / "flim.ptu"); irf = data.irf_ptu(tmp / "irf.ptu")
    truth = data.counts(1)[0].sum(0)
    vals["truth_intensity_sum"] = float(truth.sum())
    grab("before_populated_empty")
    if pid == "img_coloc":
        tif = data.tiff_pair(tmp / "pair.tif")
        m.set_filename(tif); settle(); w.run_with_progress()
    else:
        m.filename = ptu; w._on_model_event("changed") if hasattr(w, "_on_model_event") else None
        grab("before_populated_file_selected")
        if pid == "img_pixel_mle":
            m.files = [ptu]; m.irf_files = [irf]
            for k, v in {"channels_parallel_text": "0", "channels_perpendicular_text": "0"}.items():
                setattr(m, k, v)
        else:
            w.run_with_progress()
    end = time.monotonic() + 300
    settle()
    while QtCore.QThreadPool.globalInstance().activeThreadCount() and time.monotonic() < end:
        app.processEvents(); time.sleep(0.05)
    settle(60)
    if pid == "img_pixel_mle":
        pass
    else:
        vals["results_text"] = m.results_text
        for acc in ("intensity_map", "count_rate_map", "mean_micro_time_map", "g_map", "s_map", "b_map", "n_map", "epsilon_map", "number_map", "image_a", "image_b"):
            if hasattr(m, acc):
                try:
                    vals[acc] = stat(getattr(m, acc)())
                except Exception as exc:
                    vals[acc] = str(exc)
        for acc in ("metric_rows",):
            if hasattr(m, acc):
                vals[acc] = m.metric_rows()
    grab("before_populated_computed")
    grab_tabs()
    (out / "qt_values.json").write_text(json.dumps(vals, indent=1, default=str))
    print(json.dumps({k: v for k, v in vals.items() if k in ("tabs", "results_text", "truth_intensity_sum")}, default=str))



if __name__ == "__main__":
    main()
