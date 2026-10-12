"""Regenerated replacements for the hand-made guide and manual figures (all drawn by emtk, no Qt).

Each function drives the current emtk UI into the state its page describes and writes one PNG
into ``docs/guides/figures`` (the guide figures) or ``docs/manual/figures`` (the manual figures).
Run from the repository root, one function at a time::

    python docs/guides/screenshots/handmade_replacements.py ribbon_spectroscopy_imaging

Settings, MMFDB and every scratch file live in a temporary folder; the user's own preferences are
never read or written.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[3]
GUIDE_FIG = REPO / "docs" / "guides" / "figures"
MANUAL_FIG = REPO / "docs" / "manual" / "figures"
_TMP = pathlib.Path(tempfile.mkdtemp(prefix="handmade_shots_"))
os.environ["CHISURF_SETTINGS_DIR"] = str(_TMP / "settings")
os.environ["MMFDB_SETTINGS_DIR"] = str(_TMP / "mmfdb")
os.environ["MMFDB_DATABASE_PATH"] = str(_TMP / "mmfdb" / "db.sqlite")
os.environ["MMFDB_OBJECT_STORE"] = str(_TMP / "mmfdb" / "objects")
(_TMP / "settings").mkdir()
(_TMP / "mmfdb").mkdir()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(REPO))
os.chdir(REPO)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from emtk_shot import render  # noqa: E402


def ribbon_spectroscopy_imaging():
    """The shell ribbon on its Spectroscopy tab, where Imaging holds Image Tools."""
    from emtk.testing import Driver

    import time

    from chisurf.emtk.main_app import EmtkShellApp
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState

    app = EmtkShellApp()
    # A session adopted, so the Analysis dock shows the real (empty) state and not "No session".
    session = start_session(state=SessionState())
    app.data.adopt(session)
    driver = Driver(app, (1400, 860))
    end = time.monotonic() + 60.0
    while (app.data.busy or app.data._dirty) and time.monotonic() < end:
        driver.frame(1)
        time.sleep(0.02)
    driver.frame(3)
    app.ribbon.ribbon.current = "Spectroscopy"
    driver.frame(4)
    render(app, "ribbon_spectroscopy_imaging.png", driver=driver)
    return app


#: The SPC-132 smFRET DNA bursts with two detection colours (donor green 0/8, acceptor red 1/9).
_SM_DNA = REPO / "chisurf" / "plugins" / "burst" / "burst_selection" / "tests" / "data" / "bh_spc132_sm_dna"
SM_DNA_SETUP = {
    "windows": {},
    "detectors": {
        name: {"chs": chs, "micro_time_ranges": [], "g_factor": 1.0, "l1": 0.0, "l2": 0.0}
        for name, chs in (("green", [0, 8]), ("red", [1, 9]))
    },
    "tttr_reading": {"file_type": "SPC-130", "macro_time_resolution": 0.0,
                     "micro_time_resolution": 0.0, "micro_time_binning": 1},
}


def h2mm_state_decays():
    """The H2MM window on the sm-DNA bursts (two states), with every colour ticked in *Decays*."""
    import shutil
    import tempfile

    from emtk.testing import Driver

    from emtk_shot import app_from, show_tabs, wait

    work = pathlib.Path(tempfile.mkdtemp(prefix="h2mm_sm_dna_"))
    shutil.copytree(_SM_DNA, work / "sm_dna")
    app = app_from("burst_h2mm")
    m = app.model
    m.set_setup(SM_DNA_SETUP)
    m.donor, m.acceptor = "green", "red"
    driver = Driver(app, (1600, 1100))
    driver.frame(2)
    m.data_folder = str(work / "sm_dna" / "burstwise_All 0.1000#15")
    m.max_states = 2
    app.run()
    wait(driver, lambda: not app.job.busy, timeout=900)
    print("status:", m.status_text, flush=True)
    show_tabs(driver, "Decays")
    app.nano_colours = None  # every colour ticked, as the figure shows
    driver.frame(2)
    for colour in ("green", "red"):
        app.nano_colours.add(colour)
    driver.frame(3)
    render(app, "h2mm_state_decays.png", driver=driver)
    # Keep the Decays panel: the tab bar and the per-state plot, not the whole window.
    from PIL import Image

    shot = GUIDE_FIG / "h2mm_state_decays.png"
    width, height = driver.size
    Image.open(shot).crop((int(width * 0.40), int(height * 0.262), width, int(height * 0.63))).save(shot)
    print("cropped h2mm_state_decays.png", flush=True)
    app.close()


#: Manual figures of the anisotropy pages that are numbered ``image_rId*`` (the Word manual's names).
MANUAL_IMAGES = REPO / "docs" / "manual" / "_images"
_JORDI = REPO / "test" / "data" / "tcspc" / "Jordi"


def _recorded_at(path, rate_mhz):
    """A scratch copy of the recording whose footer names its laser rate (``# rep_rate: MHz``).

    The bundled files carry no metadata; a VV/VH file written by an acquisition says its rate and the
    wizard reads it into its *Repetition rate* field, which is what this copy stands in for.
    """
    import pathlib as _p
    import tempfile as _t

    folder = _p.Path(_t.gettempdir()) / "chisurf_anisotropy_recordings"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / _p.Path(path).name
    target.write_text(_p.Path(path).read_text() + f"# rep_rate: {rate_mhz}\n")
    return target


def manual_anisotropy_rid():
    """The nine ``image_rId*`` figures of the joint anisotropy analysis, from one shell session.

    Two samples (the 8 ps and the 9 ps Jordi recordings, called A488 and eGFP as the manual does) go
    through the wizard; the corrections of the first are freed, the second sample's are linked to it,
    a *Global fit* over the four polarised fits is made in the Datasets dock and run, and the result
    is reused for a third data set (the "cell").
    """
    import io
    import time

    from emtk.testing import Driver
    from PIL import Image

    from chisurf.emtk.fit_docks import ANALYSIS_KEY, DATASETS_KEY
    from chisurf.emtk.main_app import make_app
    from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.model import NativeAnisotropyModel

    out = MANUAL_IMAGES
    app = make_app(persist=False)
    driver = Driver(app, (2400, 1300))
    data = app.data

    def wait(predicate, timeout=240.0):
        end = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > end:
                import inspect

                raise TimeoutError(f"{data.status}: {inspect.getsource(predicate).strip()} busy={data.busy} dirty={data._dirty} cur={data.current_uid} fits={[r['uid'] for r in data.datasets.fits]}")
            driver.frame(1)
            time.sleep(0.03)
        driver.frame(3)

    def idle():
        return not data.busy and not data._dirty

    wait(lambda: data.session is not None and idle())
    app.docks.hide("start")

    def shell(name):
        app.pointer_move(1200.0, float(driver.size[1]) - 100.0)
        driver.frame(3)
        driver.screenshot(out / name)
        print("wrote", name, flush=True)

    def dock(name, height=None, region="left_lower"):
        original = driver.size
        app.pointer_move(1200.0, 100.0)
        driver.draw(3, size=(2000, 2400))
        x, y, w, h = (int(v) for v in app.docks.region_boxes[region])
        image = Image.open(io.BytesIO(driver.screenshot()))
        image.crop((x, y, x + w, min(y + (height or h), image.height))).save(out / name)
        driver.draw(3, size=original)
        print("wrote", name, flush=True)

    def tile(first):
        if first in data.windows:
            data.windows = {first: data.windows[first]} | {
                k: v for k, v in data.windows.items() if k != first
            }
        app.tile_fit_windows()
        driver.frame(3)

    def show(uid, focus=ANALYSIS_KEY):
        for _ in range(5):
            data.show_fit(uid)
            driver.frame(4)
            if idle() and data.current_uid == uid:
                break
        wait(lambda: idle() and data.current_uid == uid)
        app.docks.focus(focus)
        driver.frame(3)

    def run():
        data.run_fit()
        driver.frame(2)
        wait(idle)

    def wizard(label, irf, decay, bin_width, corrections=None, rotations=None):
        rate = 80.0 if bin_width < 0.0085 else 71.0  # the recording's own laser rate
        known = {r["uid"] for r in data.datasets.fits}
        m = NativeAnisotropyModel()
        m.stacked_files, m.first_column_is_time, m.use_header = True, False, False
        m.bin_width = bin_width
        m.irf_vv_path, m.data_vv_path = str(_recorded_at(irf, rate)), str(_recorded_at(decay, rate))
        m.lifetime_spectrum = [[0.5, 0.5], [0.5, 2.0]]
        m.rotation_spectrum = rotations or [[0.38, 10.0]]
        m.g_factor, m.l1, m.l2 = corrections or (1.16, 0.12, 0.44)
        assert m.load_data(), m.status
        assert m.create_fits(), m.status
        for group, role in zip(m.fit_groups, ("VV", "VH", "Global")):
            group.name = f"{label} {role}" if role != "Global" else f"{label} global"
        data._dirty |= {"fits", "windows", "current", "datasets"}
        wait(lambda: len({r["uid"] for r in data.datasets.fits} - known) >= 3 and idle())
        rows = {r["name"]: r["uid"] for r in data.datasets.fits}
        return rows[f"{label} VV"], rows[f"{label} VH"], rows[f"{label} global"]

    api = data.session.api

    def param_uid(fit_uid, name):
        info = api.get_fit_info(fit_uid=fit_uid)
        info = info.get("fit", info)
        return next(
            p["uid"] for p in info["members"][0]["parameters_all"] if p["name"] == name
        )

    def param_value(fit_uid, name):
        info = api.get_fit_info(fit_uid=fit_uid)
        info = info.get("fit", info)
        return next(
            p["value"] for p in info["members"][0]["parameters_all"] if p["name"] == name
        )

    # first sample ("A488"): its fits, the Analysis dock of the global fit (the fit list)
    a_vv, a_vh, a_glob = wizard("A488", _JORDI / "H2O_8-0 ps_2048 ch.dat",
                                _JORDI / "02_18-577+7.5uM(577)UP_8ps.dat", 0.008)
    for name in ("g", "l1", "l2"):
        api.set_parameter_fixed(name, False, fit_uid=a_vv)
    tile(a_glob)
    show(a_glob)
    run()
    dock("image_rId127.png", height=700)

    # second sample ("eGFP"), its corrections linked to the first sample's VV fit
    e_vv, e_vh, e_glob = wizard("eGFP", _JORDI / "H2O_9-1 ps_2048 ch.dat",
                                _JORDI / "02_18-577+7.5uM(577)UP_9ps.dat", 0.009)
    # "repeat all steps with the eGFP data set": its own VV/VH pair is fitted before the corrections
    # are linked -- left at the wizard's start values its windows showed chi2r 131 and 209
    tile(e_glob)
    show(e_glob)
    run()
    for name in ("g", "l1", "l2"):
        api.link_parameter(param_uid(e_vv, name), param_uid(a_vv, name), fit_uid=e_vv)
    tile(e_vv)
    show(e_vv)
    shell("image_rId135.png")
    # two fits, each polarisation pair, as the first joint fit left them
    tile(a_glob)
    show(a_glob)
    shell("image_rId133.png")

    # a new global fit over all four polarised fits, made in the Datasets dock
    app.docks.focus(DATASETS_KEY)
    glob_row = next(r for r in data.datasets.datasets if r["experiment"] == "Global")
    data.datasets.select_dataset(glob_row)
    driver.frame(3)
    assert "Global fit" in data.datasets.model_names()
    data.datasets.model = "Global fit"
    driver.frame(3)
    shell("image_rId136.png")
    known = {r["uid"] for r in data.datasets.fits}
    driver.click("datasets.add_fit")
    wait(lambda: idle() and len({r["uid"] for r in data.datasets.fits} - known) == 1)
    new_uid = next(r["uid"] for r in data.datasets.fits if r["uid"] not in known)
    app.tile_fit_windows()
    driver.frame(3)
    shell("image_rId137.png")

    # the Analysis dock follows the focused window: leave only the new global fit's window open
    for other in [u for u in data.windows if u != new_uid]:
        data.close_window(other)
    show(new_uid)
    editor = data.editor
    candidate = editor.control_for("selected_candidate_fit")
    add = editor.action_for("press", "add_selected_fit")
    names = {r["uid"]: r["name"] for r in data.datasets.fits}
    for i, uid in enumerate((a_vv, a_vh, e_vv, e_vh)):
        setattr(editor, candidate, names[uid])
        wait(idle)
        if i == 1:
            dock("image_rId138.png", height=900)
        driver.click(f"editor.{add}")
        wait(idle)
    dock("image_rId139.png", height=900)
    run()
    for uid in (a_vv, a_vh, e_vv, e_vh):
        data.show_fit(uid)
        driver.frame(3)
    tile(new_uid)
    show(new_uid)
    shell("image_rId140.png")

    # the cell: the corrections found above, one rotation, a global fit over its two polarisations
    found = [param_value(a_vv, n) for n in ("g", "l1", "l2")]
    c_vv, c_vh, c_glob = wizard("Cell", _JORDI / "H2O_9-1 ps_2048 ch.dat",
                                _JORDI / "02_18-577+7.5uM(577)UP_9ps.dat", 0.009,
                                corrections=tuple(found))
    tile(c_glob)
    show(c_glob)
    run()
    shell("image_rId143.png")
    os._exit(0)


def chimol_map_panel():
    """The ChiMOL Map panel on a density map with two contours, a filled surface and a wireframe.

    The map is ``molmap`` of the bundled T4 lysozyme at 6 A; the panel is the viewer's own
    ``density`` window (histogram with one marker per level, style, colour, exact-level entry and
    remove button), cropped out of the frame the emtk host draws.
    """
    from emtk.testing import RecordingPainter
    from PIL import Image

    from chisurf.plugins.chimol.app import make_app

    app = make_app()
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    app._ensure_chimol()
    chimol = app._chimol_app
    from chimol.plugins.demos.catalog import DEMO_DIR

    chimol.cmd.do(f'load "{DEMO_DIR / "148l.pdb"}"')
    chimol.cmd.do("molmap all, 6")
    chimol.cmd.do("density_panel on")
    gui = chimol.renderer._internal_gui
    win = next(w for w in gui.windows if w.key == "density")
    win.w, win.h, win.desired_h = 440.0, 250.0, 250.0
    panel = win.body.__self__
    model = panel.model
    low, high = model.value_range()
    levels = [dict(e) for e in model.levels][:1]
    levels[0]["style"] = "surface"
    levels.append({"level": low + 0.15 * (high - low), "color": [1.0, 0.6, 0.15, 1.0], "style": "mesh"})
    model.set_levels(levels, rebuild=True)
    panel._selected = 1
    for _ in range(6):
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
    frame = app._frame
    sx = frame.shape[1] / float(app._surface[0])
    sy = frame.shape[0] / float(app._surface[1])
    x0, y0 = int((win.x - 4) * sx), int((win.y - 2) * sy)
    x1, y1 = int((win.x + win.w + 4) * sx), int((win.y + win.h + 4) * sy)
    out = GUIDE_FIG / "chimol_map_panel.png"
    Image.fromarray(frame[y0:y1, x0:x1]).save(out)
    print("wrote", out.name, flush=True)
    app.close()
    return out


SHOTS = {
    "ribbon_spectroscopy_imaging": ("guide", ribbon_spectroscopy_imaging),
    "h2mm_state_decays": ("guide", h2mm_state_decays),
    "chimol_map_panel": ("guide", chimol_map_panel),
    "manual_anisotropy_rid": ("manual", manual_anisotropy_rid),
}


if __name__ == "__main__":
    names = sys.argv[1:] or list(SHOTS)
    for name in names:
        _, func = SHOTS[name]
        func()
    os._exit(0)
