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
}


if __name__ == "__main__":
    names = sys.argv[1:] or list(SHOTS)
    for name in names:
        _, func = SHOTS[name]
        func()
    os._exit(0)
