"""The fused tttrlib burst pipeline against the Python one: equivalence, wall time, memory, crossings.

Heavy: run it on the big machine (``ssh home``), never on a 16 GB laptop. One process per mode, so
each has its own peak RSS::

    python -m build_tools.dev_utils.fused_pipeline_equivalence run OUT/python --mode python \\
        --recipe RECIPE --settings SETTINGS --data DIR
    python -m build_tools.dev_utils.fused_pipeline_equivalence run OUT/fused --mode fused ...
    python -m build_tools.dev_utils.fused_pipeline_equivalence compare OUT/python OUT/fused
    python -m build_tools.dev_utils.fused_pipeline_equivalence figure OUT/python OUT/fused out.png

``run`` replays DNA13bp_3 as ``burst_pipeline_bench stages`` does -- the search and its burst table,
the Burst MLE session's strict background selection and its per-burst fits -- with
``CHISURF_FUSED_BURST_PIPELINE`` off (``python``) or on (``fused``), and writes ``stages.json``
(wall, peak RSS and tttrlib crossings per stage) and ``outputs.npz`` (the table, the background
patterns, the fit rows). ``--count`` makes every stage also count the calls into the tttrlib extension and the
bytes of photon arrays copied out of it (a separate run: counting inflates the wall time). ``compare`` checks the outputs
column by column. The numbers, and what they meant, are in the OKF concept
``okf/architecture/fused-burst-pipeline.md`` and tttrlib's PERF.md ("Fused burst pipeline").
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path

MEASUREMENT = "DNA13bp_3.ptu"


def _rss_gb() -> tuple[float, float]:
    """``(current, peak since the last reset)`` resident set size in GB (Linux)."""
    cur = peak = 0.0
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                cur = int(line.split()[1]) / 1e6
            elif line.startswith("VmHWM:"):
                peak = int(line.split()[1]) / 1e6
    except OSError:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    return cur, peak


def _reset_peak() -> None:
    try:
        Path("/proc/self/clear_refs").write_text("5")
    except OSError:
        pass


class _Counter:
    """Calls into the tttrlib extension and bytes of photon arrays copied out of a TTTR."""

    PHOTON_PROPS = ("macro_times", "micro_times", "routing_channels", "routing_channel", "event_types")

    def __init__(self) -> None:
        self.calls = 0
        self.bytes = 0
        self._saved: dict = {}

    def _profile(self, frame, event, arg):  # noqa: ARG002
        if event == "c_call":
            mod = getattr(arg, "__module__", None) or ""
            owner = getattr(arg, "__self__", None)
            if "_tttrlib" in mod or (owner is not None and "_tttrlib" in getattr(owner, "__name__", "")):
                self.calls += 1

    def __enter__(self):
        import numpy as np
        import tttrlib

        counter = self
        for name in self.PHOTON_PROPS:
            prop = getattr(tttrlib.TTTR, name, None)
            if not isinstance(prop, property):
                continue
            self._saved[name] = prop

            def getter(obj, _p=prop):
                value = _p.fget(obj)
                counter.bytes += int(np.asarray(value).nbytes)
                return value

            setattr(tttrlib.TTTR, name, property(getter))
        sub = tttrlib.TTTR.__getitem__
        self._saved["__getitem__"] = sub

        def getitem(obj, key, _s=sub):
            value = _s(obj, key)
            try:
                counter.bytes += 12 * len(value)  # a subset TTTR: macro, micro, routing, event
            except TypeError:
                pass
            return value

        tttrlib.TTTR.__getitem__ = getitem
        sys.setprofile(self._profile)
        return self

    def __exit__(self, *exc):
        import tttrlib

        sys.setprofile(None)
        for name, value in self._saved.items():
            setattr(tttrlib.TTTR, name, value)
        return False


#: Set by ``run --count``: every stage also counts its crossings (and its wall is inflated).
COUNT = False


def _stage(rows: list, name: str, fn):
    _reset_peak()
    base, _ = _rss_gb()
    t = time.perf_counter()
    if COUNT and name not in ("import",):
        with _Counter() as c:
            out = fn()
        crossing = {"calls": c.calls, "bytes_copied_out": c.bytes}
    else:
        out = fn()
        crossing = {}
    wall = time.perf_counter() - t
    cur, peak = _rss_gb()
    rows.append({"stage": name, "wall_s": wall, "rss_gb": cur, "peak_gb": peak,
                 "peak_over_start_gb": peak - base, **crossing})
    print(f"{name:55s} {wall:8.3f} s  peak {peak:5.2f} GB (+{peak - base:4.2f}) {crossing}", flush=True)
    return out


def run(out: Path, mode: str, recipe_path: Path, settings: Path, data: Path, count: bool) -> None:
    """Replay DNA13bp_3 in *mode* (``python`` or ``fused``)."""
    import numpy as np

    from build_tools.dev_utils.burst_pipeline_bench import _hermetic

    os.environ["CHISURF_FUSED_BURST_PIPELINE"] = "1" if mode == "fused" else "0"
    _hermetic(out, settings)
    rows: list = []
    ptu = str(data / MEASUREMENT)

    def imports():
        import tttrlib  # noqa: F401

        from chisurf.plugins.burst.burst_analysis import more_samples  # noqa: F401
        from chisurf.plugins.burst.burst_mle_analysis import engine  # noqa: F401
        from chisurf.plugins.burst.burst_selection.api import selection  # noqa: F401

    _stage(rows, "import", imports)
    import tttrlib

    from chisurf.core.fluorescence.burst import fused_pipeline
    from chisurf.core.project.analysis import container_dir
    from chisurf.plugins.burst.burst_analysis import more_samples as ms
    from chisurf.plugins.burst.burst_mle_analysis import engine

    assert fused_pipeline.enabled() == (mode == "fused"), "the switch did not take"
    recipe = ms.Recipe.from_payload(json.loads(recipe_path.read_text()))
    calibration = _stage(rows, "calibration", lambda: ms.prepare_calibration(recipe))
    folder = container_dir("")
    run_path = _stage(rows, "search (plugin: read, search, table, write the run)",
                      lambda: ms.search_task(calibration, ptu, "", str(folder)))
    session = engine.MleSession()

    def load():
        session.split_by_state = calibration.split_by_state
        session.add_burst_files([Path(run_path)])
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
        return session.current_tttr()

    photons = _stage(rows, "mle: read the run (bursts + photons)", load)

    def outside():
        from chisurf.core.fluorescence.burst import extract_mle_irf_background

        if mode == "fused":
            patterns = fused_pipeline.session_outside_patterns(session, photons, session.detectors,
                                                               irf_model="experimental")
        else:
            inside = np.zeros(len(photons), dtype=bool)
            inside[session.burst_index_array()] = True
            patterns = extract_mle_irf_background(
                photons, session.detectors, micro_time_binning=session.settings.micro_time_binning,
                mask=~inside, min_photons=max(2, int(session.settings.min_photons)),
                irf_model="experimental")
        for det, pattern in patterns.items():
            if det in session.detectors:
                session.bg_np[det] = np.asarray(pattern["bg"], dtype=float)

    _stage(rows, "mle: background outside the bursts", outside)
    strict = _stage(rows, "mle: strict background selection", session.select_background)
    workers = engine.fit_workers()
    results = _stage(rows, f"mle: run_batch ({workers} threads)", lambda: session.run_batch(max_workers=workers))
    # the burst table as written, read back
    from chisurf.core.datastore import column_names

    df = session.df_bursts
    arrays = {}
    for name in column_names(df):
        col = np.asarray(df[name])
        if col.dtype != object:
            arrays[f"table/{name}"] = col
    for det, bg in session.bg_strict_np.items():
        arrays[f"bg_strict/{det}"] = np.asarray(bg)
    for det, bg in session.bg_np.items():
        arrays[f"bg_outside/{det}"] = np.asarray(bg)
    keys = sorted({k for r in results for k in r})
    for k in keys:
        vals = [r.get(k, np.nan) for r in results]
        try:
            arrays[f"fit/{k}"] = np.asarray(vals, dtype=float)
        except (TypeError, ValueError):
            pass
    np.savez_compressed(out / "outputs.npz", **arrays)
    info = {"mode": mode, "stages": rows, "strict": strict, "n_bursts": int(len(df["First Photon"])),
            "fused_stats": fused_pipeline.last_stats, "tttrlib": getattr(tttrlib, "__version__", "?"),
            "peak_gb_process": _rss_gb()[1]}
    (out / "stages.json").write_text(json.dumps(info, indent=1, default=str))


def compare(a: Path, b: Path) -> int:
    """Column by column: identical (NaN-equal) or within the fit tolerance; returns failures."""
    import numpy as np

    x, y = np.load(a / "outputs.npz"), np.load(b / "outputs.npz")
    failures = 0
    only = sorted(set(x.files) ^ set(y.files))
    if only:
        print("only in one:", only)
        failures += len(only)
    report = {}
    for k in sorted(set(x.files) & set(y.files)):
        u, v = x[k], y[k]
        if u.shape != v.shape:
            print(f"{k}: shape {u.shape} vs {v.shape}")
            failures += 1
            continue
        same = np.array_equal(u, v, equal_nan=True) if u.dtype.kind == "f" else np.array_equal(u, v)
        if same:
            report[k] = "identical"
            continue
        if u.dtype.kind == "f":
            fin = np.isfinite(u) & np.isfinite(v)
            nan_mismatch = int(np.sum(np.isfinite(u) != np.isfinite(v)))
            rel = np.max(np.abs(u[fin] - v[fin]) / np.maximum(np.abs(u[fin]), 1e-12)) if fin.any() else 0.0
            report[k] = f"max rel {rel:.2e}, {nan_mismatch} NaN mismatches"
            tol = 1e-6 if k.startswith("fit/") else 1e-9
            if rel > tol or nan_mismatch:
                failures += 1
                print(f"{k}: {report[k]}")
        else:
            n = int(np.sum(u != v))
            report[k] = f"{n} differ"
            failures += 1
            print(f"{k}: {n} entries differ")
    sa = json.loads((a / "stages.json").read_text())
    sb = json.loads((b / "stages.json").read_text())
    print("strict:", {k: (sa["strict"].get(k), sb["strict"].get(k)) for k in sa["strict"]})
    print(f"{sum(1 for v in report.values() if v == 'identical')} of {len(report)} columns identical, "
          f"{failures} failures")
    (b / "compare.json").write_text(json.dumps({"failures": failures, "columns": report,
                                                "strict": [sa["strict"], sb["strict"]]}, indent=1))
    return failures


def _short(stage: str) -> str:
    """A stage name short enough for an axis label."""
    if stage.startswith("search"):
        return "search + table + write (plugin)"
    return stage.split(" (")[0]


def figure(a: Path, b: Path, png: Path) -> None:
    """Wall time and peak RSS per stage, Python path vs fused, side by side."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sa = json.loads((a / "stages.json").read_text())["stages"]
    sb = json.loads((b / "stages.json").read_text())["stages"]
    names = [r["stage"] for r in sa if r["stage"] not in ("import", "calibration")]
    wa = [next(r["wall_s"] for r in sa if r["stage"] == n) for n in names]
    wb = [next((r["wall_s"] for r in sb if r["stage"] == n), 0.0) for n in names]
    pa = [next(r["peak_over_start_gb"] for r in sa if r["stage"] == n) for n in names]
    pb = [next((r["peak_over_start_gb"] for r in sb if r["stage"] == n), 0.0) for n in names]
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    import numpy as np

    yy = np.arange(len(names))
    for axis, (u, v, label) in zip(ax, [(wa, wb, "wall time (s)"), (pa, pb, "peak RSS above stage start (GB)")]):
        axis.barh(yy + 0.2, u, 0.4, label="Python path", color="#8c8c8c")
        axis.barh(yy - 0.2, v, 0.4, label="fused BurstPipeline", color="#2a6fbb")
        axis.set_yticks(yy)
        axis.set_yticklabels([_short(n) for n in names] if axis is ax[0] else [])
        axis.invert_yaxis()
        axis.set_xlabel(label)
        axis.grid(axis="x", alpha=0.3)
    ax[1].legend(loc="upper right")
    fig.suptitle("DNA13bp_3.ptu (12 M photons), ssh home: Python burst pipeline vs fused tttrlib pass")
    fig.tight_layout()
    fig.savefig(png, dpi=130)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("out", type=Path)
    r.add_argument("--mode", choices=("python", "fused"), required=True)
    r.add_argument("--recipe", type=Path, required=True)
    r.add_argument("--settings", type=Path, required=True)
    r.add_argument("--data", type=Path, required=True)
    r.add_argument("--count", action="store_true")
    c = sub.add_parser("compare")
    c.add_argument("a", type=Path)
    c.add_argument("b", type=Path)
    f = sub.add_parser("figure")
    f.add_argument("a", type=Path)
    f.add_argument("b", type=Path)
    f.add_argument("png", type=Path)
    args = p.parse_args(argv)
    if args.cmd == "run":
        global COUNT
        COUNT = bool(args.count)
        run(args.out, args.mode, args.recipe, args.settings, args.data, args.count)
        return 0
    if args.cmd == "compare":
        return 1 if compare(args.a, args.b) else 0
    figure(args.a, args.b, args.png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
