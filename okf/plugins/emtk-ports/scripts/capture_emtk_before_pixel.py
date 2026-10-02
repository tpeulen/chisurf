"""The stream's emtk app (as committed in the baseline commit) on the shared synthetic photon stream: before_emtk_*.png. Usage: <plugin_id> <out_dir>."""
import os, pathlib, sys, tempfile, time

tmp = pathlib.Path(tempfile.mkdtemp())
os.environ.update(CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"), HOME=str(tmp / "home"))
(tmp / "home").mkdir()


def main():
    from emtk.testing import PixelPainter, png_encode
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import imaging_pixel_data as data
    from test.gui.emtk_port_parity import build_emtk_app
    pid, out = sys.argv[1], pathlib.Path(sys.argv[2])
    app = build_emtk_app(pid)

    def shot(name, size):
        for _ in range(3):
            p = PixelPainter(*size); app.draw(p, 0, 0, *size)
        (out / name).write_bytes(png_encode(p.width, p.height, p.px))

    shot("before_emtk_empty_1200x800.png", (1200, 800))
    if pid == "img_coloc":
        f = data.tiff_pair(tmp / "pair.tif"); app.model.set_filename(f); app.start("compute_job") if hasattr(app, "start") else None
    elif pid == "img_pixel_mle":
        f = data.flim_ptu(tmp / "flim.ptu"); app.model.files = [f]; app.model.irf_files = [data.irf_ptu(tmp / "irf.ptu")]
    else:
        f = data.flim_ptu(tmp / "flim.ptu"); app.model.load_file(f) if pid != "img_coloc" else None
        if hasattr(app, "start"):
            app.start("compute_job")
    end = time.monotonic() + 120
    while getattr(getattr(app, "job", None), "busy", False) and time.monotonic() < end:
        time.sleep(0.05)
        shot("tmp.png", (200, 200))
    for _ in range(5):
        shot("tmp.png", (200, 200))
    shot("before_emtk_populated_1200x800.png", (1200, 800)); shot("before_emtk_populated_800x600.png", (800, 600))
    (out / "tmp.png").unlink(missing_ok=True)
    print("ok", getattr(app.model, "results_text", ""))


if __name__ == "__main__":
    main()
