"""Guide figures of emtk plugin windows: F-test, HydroPro, Ask the documentation, the AI assistant,
the burst export table and the ChiMOL Objects panel.

    IMP_BFF_GPU=off python docs/guides/screenshots/guides_plugins_emtk.py [name ...]

Names: ``f_test``, ``hydropro``, ``help``, ``assistant``, ``export_table``, ``chimol``. Read every PNG.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
os.chdir(pathlib.Path(__file__).resolve().parents[3])
os.environ.setdefault("CHISURF_SETTINGS_DIR", tempfile.mkdtemp(prefix="chisurf_plugin_shots_"))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[3]
FIG = REPO / "docs" / "guides" / "figures"
IBH = REPO / "test" / "data" / "tcspc" / "ibh_sample"
PDB_148L = REPO / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"


def _driver(app, size):
    from emtk.testing import Driver

    driver = Driver(app, size)
    driver.frame(3)
    return driver


def _close(app):
    close = getattr(app, "close", None)
    if callable(close):
        close()


def _save(driver, name, frames=3):
    driver.frame(frames)
    driver.screenshot(FIG / name)
    print("wrote", name, flush=True)


def _grab_f_test() -> None:
    """F-test fed from real fits: 1- vs 2-exponential donor-only decay."""
    import warnings

    from chisurf.core.fluorescence.decay_fit_model import build_lifetime_fit
    from chisurf.plugins.core.f_test.gui.app import FTestApp

    dt = 0.0141 * 8
    decay = np.loadtxt(IBH / "Decay_577D.txt", skiprows=9)[:, 1].reshape(-1, 8).sum(1)
    irf = np.clip(np.loadtxt(IBH / "Prompt.txt", skiprows=9)[:, 1] - 0, 0, None)
    irf = np.clip(irf - np.median(irf[-800:]), 0, None).reshape(-1, 8).sum(1)
    warnings.simplefilter("ignore")
    fits = []
    for n in (1, 2):
        fit = build_lifetime_fit(
            decay, bin_width=dt, irf=irf, n_components=n,
            initial_lifetimes=[0.5, 2.0, 4.5][-n:], fit_background=True, start_bin=55, stop_bin=480,
        )
        fit.run()
        fits.append(fit)
    app = FTestApp(fit_provider=lambda: fits)
    driver = _driver(app, (1000, 500))
    app.load_fit_into(0, "model1")
    app.load_fit_into(1, "model2")
    app.load_fit_into(1, "chi2max")
    m = app.model
    print("ftest", m.chi2_1, m.n1, m.chi2_2, m.n2, m.conf_level, m.chi2_min, m.npars, m.dof, m.chi2_max)
    _save(driver, "f_test_tool.png")
    _close(app)


def _grab_hydropro() -> None:
    """HydroPro with 148L selected and T4 lysozyme's mass and v-bar; the executable prompt."""
    from chisurf.plugins.modelling.hydropro.app import HydroProApp

    app = HydroProApp()
    m = app.model
    m.exe_path = ""
    m.files_chosen([str(PDB_148L)])
    m.rm = 18700.0
    m.vbar = 0.73
    m.status = "Executable not configured"
    driver = _driver(app, (1200, 800))
    _save(driver, "hydropro_tool.png")
    m.exe_prompt = True
    driver.frame(3)
    driver.frame(3)
    driver.screenshot(FIG / "_hydropro_full.png")
    from PIL import Image

    full = FIG / "_hydropro_full.png"
    Image.open(full).convert("RGB").crop((326, 270, 874, 418)).save(FIG / "hydropro_exe_dialog.png")
    full.unlink()
    print("wrote hydropro_exe_dialog.png", flush=True)
    _close(app)


def _grab_help() -> None:
    """Ask the documentation: the answer layout with its citations, beside the page it cited."""
    from emtk.testing import Driver  # noqa: F401

    from chisurf.core.agent import doc_index
    from chisurf.plugins.core.help.gui.help_app import HelpApp

    app = HelpApp()
    model = app.model
    page = doc_index.resolve("docs/concepts/accurate_fret.md")
    if page is not None:
        model.open_page(pathlib.Path(page))
    app.help_gui.show_ask()
    model.chat_history.add_message("user", "What does the gamma correction factor do?")
    model.chat_history.add_message(
        "assistant",
        "The γ factor corrects the raw green/red photon ratio for the two things that make the two "
        "channels not comparable: the detection efficiencies of the donor and acceptor detection "
        "paths, and the fluorescence quantum yields of the two dyes.\n\n"
        "Without it the proximity ratio is not a FRET efficiency, and the populations in an E–S "
        "histogram sit in the wrong place. All four factors and where each comes from are in "
        "[The four factors](docs/concepts/accurate_fret.md#The four factors); the workflow that "
        "determines them is [Accurate FRET corrections](docs/guides/41_accurate_fret.md).\n\n"
        "**Cited Documentation Pages:**\n"
        "- [Accurate FRET: correction factors, FRET lines, and where they come from]"
        "(docs/concepts/accurate_fret.md)\n"
        "- [Accurate FRET: automatic correction factors](docs/guides/41_accurate_fret.md)",
    )
    model.chat_history.finish_generation("complete")
    driver = _driver(app, (1500, 900))
    _save(driver, "ask_the_documentation.png", frames=6)
    _close(app)


def _grab_assistant() -> None:
    """The assistant in the mode that operates ChiSurf, with a placed (not run) tool-driven transcript."""
    from chisurf.plugins.core.code_editor.gui.chat_app import ChatApp

    app = ChatApp()
    model = app.chat_gui.model
    model.mode = "chisurf_tools"
    history = model.history
    history.add_message("user", "Fit the decays in test/data/tcspc/ibh and tell me the lifetimes.")
    for line in (
        "load_data(path='test/data/tcspc/ibh')  ->  3 dataset(s)",
        "add_fit(model='Lifetime', dataset=0..2)  ->  3 fits",
        "run_fit(all)  ->  chi2r = 1.03, 1.12, 0.98",
    ):
        history.add_message("system", line)
    history.add_message(
        "assistant",
        "All three converged. The donor-only sample gives 3.81 ns; the two labelled samples give "
        "2.34 ns and 1.61 ns, so the transfer efficiencies are 0.39 and 0.58. The fits are in your "
        "window — chi2r is 0.98-1.12, so none of them is straining. Ask me to add a second "
        "component if the residuals look structured.",
    )
    history.finish_generation("complete")
    driver = _driver(app, (980, 720))
    _save(driver, "ai_assistant.png", frames=5)
    _close(app)


def _grab_chimol() -> None:
    """The ChiMOL Objects panel: ligand and peptidoglycan split off 148L, then two groups (one collapsed)."""
    from emtk.testing import RecordingPainter
    from PIL import Image

    from chisurf.plugins.chimol.app import make_app

    app = make_app()
    size = (1200, 800)

    def draw(n=4):
        for _ in range(n):
            app.draw(RecordingPainter(), 0, 0, *size)

    draw(1)
    app._ensure_chimol()
    chimol = app._chimol_app
    from chimol.plugins.demos.catalog import DEMO_DIR

    messages = []
    chimol.cmd.set_error_callback(lambda m: messages.append(m))
    chimol.cmd.do(f'load "{DEMO_DIR / "148l.pdb"}"')
    for line in ("extract lig, resn BME", "extract nag, resn NAG+MUB"):
        chimol.cmd.do(line)
    draw()

    def panel(name):
        gui = chimol.renderer._internal_gui
        win = next(w for w in gui.windows if w.key == "objects")
        win.w = 440.0
        draw(3)
        frame = app._frame
        sx = frame.shape[1] / float(app._surface[0])
        sy = frame.shape[0] / float(app._surface[1])
        x0, y0 = int((win.x - 4) * sx), int((win.y - 2) * sy)
        x1, y1 = int((win.x + win.w + 4) * sx), int((win.y + win.h + 4) * sy)
        Image.fromarray(frame[y0:y1, x0:x1]).save(FIG / name)
        print("wrote", name, flush=True)

    draw()
    panel("chimol_objects_panel.png")
    for line in ("extract nterm, resi 1-60", "extract cterm, resi 61-164",
                 "group ligands, lig nag", "group parts, nterm cterm", "group parts, close"):
        chimol.cmd.do(line)
    draw(6)
    panel("chimol_groups_panel.png")
    print("errors:", messages, flush=True)
    _close(app)


def _grab_export_table() -> None:
    """The per-burst export table, as `build_tables` writes it, on a simulated two-state trace.

    Bursts alternate between E = 0.25 and E = 0.75, so `Dominant State` must alternate 0/1 in step
    with `Proximity ratio`: the figure checks the export and the H2MM fit behind it.
    """
    import tttrlib
    from emtk.app import ImApp
    from emtk.widgets.data_table import TableBinding, draw_table
    from emtk import im

    from chisurf.core.datastore import column_names, column_values
    from chisurf.plugins.burst.burst_h2mm.core import engines as h2mm_engines
    from chisurf.plugins.burst.burst_h2mm.core import export as burst_export
    from chisurf.plugins.burst.burst_h2mm.core.photons import StreamDef, bursts_from_dataframe

    rng = np.random.default_rng(0)
    macro, micro, channel, rows = [], [], [], []
    clock = 0
    for index in range(40):
        n_photons = int(rng.integers(60, 160))
        efficiency = 0.25 if index % 2 == 0 else 0.75
        start = len(macro)
        for _ in range(n_photons):
            clock += int(rng.integers(1, 40))
            macro.append(clock)
            red = rng.random() < efficiency
            channel.append(1 if red else 0)
            micro.append(int(rng.integers(100, 500) if red else rng.integers(200, 900)))
        rows.append(("sim.spc", start, len(macro) - 1))
        clock += 5000
    tttr = tttrlib.TTTR()
    tttr.append_events(
        np.asarray(macro, np.uint64), np.asarray(micro, np.uint16), np.asarray(channel, np.int8),
        np.zeros(len(macro), np.int8), False, 0,
    )
    frame = {
        "First File": [row[0] for row in rows],
        "First Photon": np.array([row[1] for row in rows], dtype=np.int64),
        "Last Photon": np.array([row[2] for row in rows], dtype=np.int64),
    }
    data, meta = bursts_from_dataframe(
        frame, {"sim.spc": tttr}, [StreamDef("green", [0]), StreamDef("red", [1])],
        min_photons=1, return_meta=True,
    )
    fit = h2mm_engines.fit_states(data, 2, n_restarts=1, max_iter=200, seed=0)
    path, _ = h2mm_engines.viterbi(fit, data)
    tables = burst_export.build_tables(
        data, meta, path, np.array([0.25, 0.75]), base_time_s=1e-6, micro_time_ns=0.032,
        stream_groups=[("green", (0,)), ("red", (1,))],
    )
    bursts = tables.bursts
    names = column_names(bursts)
    columns = {n: np.asarray(column_values(bursts, i), dtype=float) for i, n in enumerate(names)}
    print("columns", names, flush=True)

    class Owner:
        table = columns

    binding = TableBinding({"type": "custom", "key": "data_table", "options": {
        "source": "table", "fit_columns": True, "min_column_width": 60}}, Owner())
    size = (1460, 430)

    def gui() -> None:
        vp = im.get_main_viewport()
        im.set_next_window_pos(vp.pos, im.Cond.ALWAYS)
        im.set_next_window_size(vp.size, im.Cond.ALWAYS)
        if im.begin("Burst export table", (*vp.pos, *vp.size)):
            draw_table(binding, "burst_export", width=size[0] - 16, height=size[1] - 40)
        im.end()

    app = ImApp(gui)
    driver = _driver(app, size)
    _save(driver, "burst_export_table.png", frames=4)


GRABS = {"f_test": _grab_f_test, "hydropro": _grab_hydropro, "help": _grab_help,
         "assistant": _grab_assistant, "chimol": _grab_chimol, "export_table": _grab_export_table}

if __name__ == "__main__":
    for key in sys.argv[1:] or GRABS:
        GRABS[key]()
    os._exit(0)
