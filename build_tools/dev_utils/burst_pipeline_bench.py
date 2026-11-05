"""Where the wall time of the Burst Analysis pipeline goes: per step, per frame, per stage.

Heavy: run it on the big machine (``ssh home``), never on a 16 GB laptop -- a replay holds the
measurement several times. Three sub-commands::

    # the hub driven as a user would (headless, test painter): wall per step, frame time per
    # step and per Burst MLE tab, cProfile of those frames; writes timing.json + recipe.json;
    # --think: Next only once the search ahead (and Burst MLE ahead of it) is done
    python -m build_tools.dev_utils.burst_pipeline_bench gui OUT --settings SETTINGS --data DIR \
        [--think]

    # the same pipeline stage by stage, headless, each beside the raw engine call it wraps;
    # optionally the More samples batch on N links of the measurement
    python -m build_tools.dev_utils.burst_pipeline_bench stages OUT --recipe OUT/recipe.json \
        --settings SETTINGS --data DIR [--batch 3]

    # stacked bar of the per-step wall, before and after
    python -m build_tools.dev_utils.burst_pipeline_bench figure BEFORE/timing.json \
        AFTER/timing.json out.png

*SETTINGS* is a ChiSurf settings folder holding the detector setup (``RVZMT150`` by default,
``--setup``), copied into *OUT* first; *DIR* holds ``DNA13bp_3.ptu``, ``Rh110_thick_1.ptu`` and
``Alexa647_thick_1.ptu`` (copy them off an SD card first: the card's reads would be measured).
``CHISURF_FIT_WORKERS`` caps the fit threads (and the More samples processes). The numbers, and
what they meant, are kept in the OKF concept ``okf/plugins/burst.md`` ("Pipeline wall time").
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import os
import pstats
import shutil
import sys
import time
from pathlib import Path

#: The steps of :func:`gui`, in order: the stacked bar's segments (``think``: with ``--think``,
#: the time the user spends at the search settings while the pipeline works ahead).
STEPS = ("shell", "hub open", "data+calibration", "think", "search", "mle ready", "mle fit")
MEASUREMENT = "DNA13bp_3.ptu"
REFERENCES = ("Rh110_thick_1.ptu", "Alexa647_thick_1.ptu")


def _hermetic(out: Path, settings: Path) -> None:
    """A copy of *settings* in *out*, and every ChiSurf store pointed into *out*."""
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    shutil.copytree(settings, out / "settings")
    os.environ["CHISURF_SETTINGS_DIR"] = str(out / "settings")
    os.environ["MMFDB_DATABASE_PATH"] = str(out / "settings" / "flr" / "sample_management.db")
    os.environ["CHISURF_ANALYSIS_DIR"] = str(out / "analysis")


def _median_ms(samples: list[float]) -> float:
    samples = sorted(samples)
    return 1e3 * samples[len(samples) // 2] if samples else float("nan")


def gui(out: Path, settings: Path, data: Path, setup: str = "RVZMT150", frames: int = 30,
        think: bool = False) -> dict:
    """Drive the hub through setup, data (with the two reference dyes), search and Burst MLE."""
    _hermetic(out, settings)
    t0 = time.perf_counter()
    marks: list[tuple[str, float]] = []

    def mark(name: str) -> None:
        marks.append((name, time.perf_counter() - t0))
        print(f"[{marks[-1][1]:8.2f}] {name}", flush=True)

    from emtk.testing_realistic import RealisticDriver

    from chisurf.emtk.main_app import EmtkShellApp
    from chisurf.emtk.session import start_session
    from chisurf.plugins.burst.burst_analysis.gui.native import receive_photons

    def busy(child) -> bool:
        return any(getattr(o, n, False) is True
                   for o in (child, getattr(child, "controller", None), getattr(child, "job", None))
                   for n in ("running", "busy"))

    mark("imports")
    shell = EmtkShellApp(console_history=False, console_session_file=False)
    shell.data.adopt(start_session())
    drv = RealisticDriver(shell, (1440, 900), real_painter=False)
    drv.frame(3)
    mark("shell")

    def wait(pred, what: str, timeout: float = 1800.0) -> None:
        end = time.monotonic() + timeout
        while not pred():
            if time.monotonic() > end:
                raise TimeoutError(what)
            drv.frame(1)
            time.sleep(0.02)
        drv.frame(3)

    handle = shell.open_plugin("burst_analysis")
    wait(lambda: handle.build is None and handle.box is not None, "hub")
    hub = handle.app

    def settle() -> None:
        wait(lambda: not any(busy(c) for c in hub.children.values()) and not hub._pending_next,
             "settle")

    mark("hub open")
    hub.select("setup")
    drv.frame(1)
    hub.children["setup"].select_setup(setup)
    drv.frame(1)
    receive_photons(hub, {"files": [str(data / MEASUREMENT), *(str(data / r) for r in REFERENCES)],
                          "datasets": []})
    drv.frame(1)
    settle()
    wait(lambda: not hub.children["data"].job.busy, "calibration")
    mark("data+calibration")
    hub.select("selection")
    drv.frame(3)
    selection = hub.children["selection"]
    if think:
        # the user looks at the search settings: the search ahead lands (and, where the pipeline
        # runs it, Burst MLE prepares and fits ahead) before Next
        def ahead_done() -> bool:
            if selection.model.ahead is None:
                return False
            if not hasattr(hub, "_mle_ahead"):
                return True  # a tree whose Burst MLE does not run ahead
            mle_child = hub.children.get("mle")
            return (mle_child is not None and getattr(mle_child, "ahead_key", None) is not None
                    and not mle_child.pending)

        wait(ahead_done, "search ahead")
        mark("think")
    selection.run()
    wait(lambda: not selection.running and hub.context.bur_files, "search")
    mark("search")
    hub.select("mle")
    drv.frame(1)
    mle = hub.children["mle"]
    wait(lambda: not mle.pending, "mle ready")
    mark("mle ready")
    mle.fit_bursts()
    drv.frame(1)
    wait(lambda: not mle.job.busy, "fit")
    settle()
    mark("mle fit")
    recipe = hub.capture_recipe()
    (out / "recipe.json").write_text(json.dumps(recipe.to_payload() if recipe else None, default=str))

    def frame_ms(n: int = frames) -> float:
        times = []
        for _ in range(n):
            a = time.perf_counter()
            drv.frame(1)
            times.append(time.perf_counter() - a)
        return _median_ms(times)

    frame_cost: dict[str, float] = {}
    for role in ("setup", "data", "selection", "mle", "more"):
        hub.select(role)
        drv.frame(5)
        settle()
        frame_cost[role] = frame_ms()
    hub.select("mle")
    drv.frame(5)
    for tab in ("decay", "inspect", "results"):
        mle.docks.focus(tab)
        drv.frame(5)
        frame_cost[f"mle:{tab}"] = frame_ms()
        profile = cProfile.Profile()
        profile.enable()
        drv.frame(15)
        profile.disable()
        text = io.StringIO()
        pstats.Stats(profile, stream=text).sort_stats("cumulative").print_stats(40)
        (out / f"frame_{tab}.txt").write_text(text.getvalue())
    for name, ms in frame_cost.items():
        print(f"frame {name:12s} {ms:8.2f} ms", flush=True)
    result = {"marks": marks, "frames_ms": frame_cost,
              "bursts": int(getattr(mle.model, "n_bursts", 0))}
    (out / "timing.json").write_text(json.dumps(result, indent=1))
    shell.close()
    return result


class _Stage:
    """``with _Stage(rows, name):`` -- wall of the block into *rows*, its cProfile beside."""

    def __init__(self, rows: list, out: Path, name: str, profile: bool = True) -> None:
        self.rows, self.out, self.name, self.profile = rows, out, name, profile

    def __enter__(self):
        self.pr = cProfile.Profile() if self.profile else None
        self.t = time.perf_counter()
        if self.pr:
            self.pr.enable()
        return self

    def __exit__(self, *exc) -> None:
        if self.pr:
            self.pr.disable()
        dt = time.perf_counter() - self.t
        self.rows.append((self.name, dt))
        print(f"{self.name:52s} {dt:8.3f} s", flush=True)
        if self.pr:
            text = io.StringIO()
            pstats.Stats(self.pr, stream=text).sort_stats("cumulative").print_stats(40)
            slug = "".join(c if c.isalnum() else "_" for c in self.name)
            (self.out / f"{slug}.txt").write_text(text.getvalue())


def stages(out: Path, settings: Path, data: Path, recipe_path: Path, batch: int = 0) -> list:
    """The pipeline headless, stage by stage, each beside its raw engine call."""
    import copy

    import numpy as np

    _hermetic(out, settings)
    rows: list = []

    def stage(name: str, profile: bool = True) -> _Stage:
        return _Stage(rows, out, name, profile)

    ptu = str(data / MEASUREMENT)
    with stage("import", profile=False):
        import tttrlib

        from chisurf.core.fluorescence.burst import extract_mle_irf_background
        from chisurf.core.project.analysis import container_dir
        from chisurf.plugins.burst.burst_analysis import more_samples as ms
        from chisurf.plugins.burst.burst_mle_analysis import _mp_worker as worker
        from chisurf.plugins.burst.burst_mle_analysis import engine
        from chisurf.plugins.burst.burst_selection.api import selection as sel_api
        from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel
    recipe = ms.Recipe.from_payload(json.loads(recipe_path.read_text()))
    with stage("raw: tttrlib.TTTR read", profile=False):
        tttr = tttrlib.TTTR(ptu)
    with stage("calibration: prepare_calibration"):
        calibration = ms.prepare_calibration(recipe)
    folder = container_dir("")
    with stage("plugin: search (read, search, filter, write the run)"):
        run = ms.search_task(calibration, ptu, "", str(folder))
    model = BurstSelectionModel()
    model.set_setup({**calibration.setup, "setup_name": recipe.setup_name})
    model.import_settings(recipe.selection)
    settings_ = model.analysis_settings()
    with stage("raw: photon filter + find_bursts"):
        selected = sel_api.apply_photon_filters(tttr, settings_.photon_filter,
                                                burst_detection=settings_.burst_detection)
        gap = settings_.photon_filter.max_gap if settings_.photon_filter.use_gap_fill else 0
        sel_api.drop_short_bursts(sel_api.find_bursts(selected, max_gap=gap),
                                  max(2, settings_.burst_detection.min_photons))
    session = engine.MleSession()
    with stage("mle: read the run (bursts + photons)"):
        session.split_by_state = calibration.split_by_state
        session.add_burst_files([Path(run)])
        session.set_definition(calibration.setup)
    known = set(engine.MleSettings.__dataclass_fields__)
    for det, values in calibration.det_settings.items():
        if det in session.detectors:
            session.det_settings[det] = engine.MleSettings(
                **copy.deepcopy({k: v for k, v in values.items() if k in known}))
    for det, irf in calibration.irf.items():
        if det in session.detectors:
            session.irf_np[det] = irf
    for det, entry in calibration.shift_calibration.items():
        if det in session.detectors:
            session.shift_calibration[det] = dict(entry)
    session.outcome = None
    photons = session.current_tttr()
    with stage("mle: background outside the bursts + strict selection"):
        inside = np.zeros(len(photons), dtype=bool)
        inside[session.burst_index_array()] = True
        patterns = extract_mle_irf_background(
            photons, session.detectors, micro_time_binning=session.settings.micro_time_binning,
            mask=~inside, min_photons=max(2, int(session.settings.min_photons)),
            irf_model="experimental")
        for det, pattern in patterns.items():
            if det in session.detectors:
                session.bg_np[det] = np.asarray(pattern["bg"], dtype=float)
        session.select_background()
    workers = engine.fit_workers()
    with stage(f"mle: run_batch ({workers} threads, fit_many)", profile=False):
        session.run_batch(max_workers=workers)
    with stage("mle: export_results"):
        session.export_results()
    # raw fit2x on the same decays: one C++ call for many bursts vs the per-burst Python loop
    det = next(iter(session.detectors))
    cfg = session.batch_config(det)
    half = max(1, cfg["irf"].size // 2)
    binning = int(session.settings.micro_time_binning)
    rc = np.asarray(photons.routing_channels)
    mt = (np.asarray(photons.micro_times) // binning).astype(np.uint16)
    chs = session.detectors[det]["chs"]
    lut = np.full(int(rc.max()) + 1, -1, np.int8)
    lut[chs[::2]] = 0
    lut[chs[1::2]] = 1
    first = engine.numeric_column(session.df_bursts, "First Photon").astype(int)
    last = engine.numeric_column(session.df_bursts, "Last Photon").astype(int)
    s0, s1 = max(0, int(cfg["sb"])), min(half, int(cfg["eb"]))
    decays = np.zeros((first.size, 2 * half))
    with stage("raw: per-burst decay histograms", profile=False):
        for i in range(first.size):
            cp, cs = worker._hist2_split_core_classlut(mt[first[i]:last[i] + 1],
                                                       rc[first[i]:last[i] + 1], lut, half)
            decays[i, s0:s1] = cp[s0:s1]
            decays[i, half + s0:half + s1] = cs[s0:s1]
    cfg["dt"], cfg["period"] = session.timing_ns(photons, binning)
    fitter = worker._build_fitter(cfg)
    rows_fit = decays[decays.sum(1) >= int(cfg["min_photons"])][:5000]
    with stage(f"raw: fit2x per-burst loop ({len(rows_fit)} decays, 1 core)", profile=False):
        for row in rows_fit:
            fitter(data=row, initial_values=cfg["x0"], fixed=cfg["fixed"])
    with stage(f"raw: fit2x fit_many ({len(rows_fit)} decays, one call)", profile=False):
        fitter.fit_many(rows_fit, cfg["x0"], fixed=cfg["fixed"])
    with stage("write the recipe and report"):
        ms.write_recipe(ptu, calibration, folder, runs=[run])
    if batch:
        links = out / "batch"
        links.mkdir()
        paths = []
        for i in range(batch):
            link = links / f"{Path(ptu).stem}_copy{i}.ptu"
            os.symlink(ptu, link)
            paths.append(link)
        with stage(f"batch: More samples, {batch} samples", profile=False):
            done = ms.process_more(recipe, paths, register=False)
        print([(d["name"], d["status"], d["bursts"], d.get("error")) for d in done])
    (out / "stages.json").write_text(json.dumps(rows, indent=1))
    return rows


def figure(before: Path, after: Path, png: Path) -> None:
    """Stacked bar of the per-step wall of two :func:`gui` runs, with the frame times beside."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    runs = {}
    for label, path in (("before", before), ("after", after)):
        data = json.loads(Path(path).read_text())
        at = dict(data["marks"])
        previous, segments = 0.0, {}
        for name in STEPS:
            if name in at:
                segments[name] = at[name] - previous
                previous = at[name]
        frames_ms = {k: (v[0] if isinstance(v, (list, tuple)) else v)
                     for k, v in (data.get("frames_ms") or data.get("frames") or {}).items()
                     if not k.startswith("inspect")}
        runs[label] = (segments, frames_ms)
    fig, (bars, frames) = plt.subplots(1, 2, figsize=(11, 5.2), gridspec_kw={"width_ratios": [1, 1.3]})
    colours = plt.get_cmap("tab10").colors
    for x, (label, (segments, _f)) in enumerate(runs.items()):
        bottom = 0.0
        for i, name in enumerate(STEPS):
            value = segments.get(name, 0.0)
            bars.bar(x, value, bottom=bottom, color=colours[i], label=name if x == 0 else None,
                     width=0.6, edgecolor="white")
            if value > 2:
                bars.text(x, bottom + value / 2, f"{value:.0f} s", ha="center", va="center",
                          fontsize=8, color="white")
            bottom += value
        bars.text(x, bottom + 1, f"{bottom:.0f} s", ha="center", va="bottom", fontsize=9)
    bars.set_xticks(range(len(runs)), list(runs))
    bars.set_ylabel("wall time per step [s]")
    bars.set_title("Burst Analysis, DNA13bp_3: wall per step")
    bars.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3, frameon=False)
    bars.set_ylim(0, max(sum(seg.values()) for seg, _f in runs.values()) * 1.1)
    names = [n for n in runs["before"][1] if n in runs["after"][1]]
    ys = range(len(names))
    frames.barh([y + 0.2 for y in ys], [runs["before"][1][n] for n in names], height=0.4,
                label="before", color="0.6")
    frames.barh([y - 0.2 for y in ys], [runs["after"][1][n] for n in names], height=0.4,
                label="after", color=colours[0])
    frames.set_yticks(list(ys), names)
    frames.invert_yaxis()
    frames.set_xlabel("median frame time [ms] (test painter)")
    frames.set_title("frame time per step / Burst MLE tab")
    frames.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(png, dpi=130)


def main(argv: list[str] | None = None) -> int:
    """Command line: ``gui``, ``stages`` or ``figure``."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("gui", "stages"):
        p = sub.add_parser(name)
        p.add_argument("out", type=Path)
        p.add_argument("--settings", type=Path, required=True)
        p.add_argument("--data", type=Path, default=Path(os.environ.get("DATA", ".")))
        if name == "gui":
            p.add_argument("--setup", default="RVZMT150")
            p.add_argument("--think", action="store_true",
                           help="wait for the search ahead (and Burst MLE ahead) before Next")
        else:
            p.add_argument("--recipe", type=Path, required=True)
            p.add_argument("--batch", type=int, default=0)
    p = sub.add_parser("figure")
    p.add_argument("before", type=Path)
    p.add_argument("after", type=Path)
    p.add_argument("png", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "gui":
        gui(args.out.resolve(), args.settings, args.data, args.setup, think=args.think)
    elif args.cmd == "stages":
        stages(args.out.resolve(), args.settings, args.data, args.recipe, args.batch)
    else:
        figure(args.before, args.after, args.png)
    return 0


if __name__ == "__main__":
    # spawned workers re-import __main__: only the parent runs the benchmark
    sys.exit(main())
