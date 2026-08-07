"""Does every writer leave a container whose lineage reconstructs?

Drives the **real** writers against real data and asks, of every artifact each
one leaves behind, whether it names its operation, its settings and its
parents, and whether the walk terminates at the primary data.

Deliberately a script rather than a test, for now: it is the working half of
[PRD-88](/prds/prd-88.md), whose first task is to turn it into one. Kept because
it is cheap and it finds things -- roughly 200 lines, and on its first run it
found 6 of 26 artifacts with a broken or incomplete lineage, four of them a
single root cause that the whole container migration had missed.

Run it::

    QT_QPA_PLATFORM=offscreen python -m build_tools.dev_utils.lineage_audit

A writer with no fixture to drive it is reported as *not exercised* rather than
skipped quietly: a cell nothing covers is a finding.
"""
import shutil
import tempfile
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

from chisurf.core.fio.pto import Measurement

DATA = Path("chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna")
PTU = Path("test/data/clsm/Leica_SP5.ptu")


def fresh(name="m000.spc"):
    tmp = Path(tempfile.mkdtemp())
    src = tmp / name
    src.write_bytes((DATA / "m000.spc" if name.endswith(".spc") else PTU).read_bytes())
    return tmp, src


def audit(container, label, results):
    """Report every artifact that cannot say where it came from."""
    with Measurement.open(container) as m:
        primary = m.instrument_uid
        for obj in m.artifacts():
            if obj.uid == primary or obj.kind in ("readme", "sample_metadata"):
                continue
            step = m.provenance(obj.uid)
            problems = []
            if not step["operation"]:
                problems.append("no operation")
            if not step["settings"]:
                problems.append("no settings")
            if not step["parents"]:
                problems.append("no parents")
            else:
                walk = m.lineage(obj.uid)
                if walk[-1]["uid"] != primary:
                    problems.append(f"walk ends at {walk[-1]['name']!r}")
            results.append((label, obj.name, problems))


def bursts(n=20):
    return pd.DataFrame(
        {
            "First File": ["x"] * n,
            "Burst": np.arange(n),
            "Number of Photons": np.arange(n) * 10 + 50,
            "Duration (ms)": np.linspace(0.5, 5.0, n),
        }
    )


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def burst_selection(results):
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    tmp, src = fresh()
    write_container(src, bursts(), parameters={"min_photons": 60})
    audit(src.with_suffix(".pto"), "burst_selection", results)
    shutil.rmtree(tmp)


@case
def burst_mle(results):
    from chisurf.plugins.burst.burst_mle_analysis.core.export import write_mle_container

    tmp, src = fresh()
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    write_container(src, bursts(), parameters={"min_photons": 60})
    tables = {
        "Green": pd.DataFrame({"Tau (green)": np.linspace(1, 4, 20)}),
        "Red": pd.DataFrame({"Tau (red)": np.linspace(1, 4, 20)}),
    }
    states = [{"Detector": "Green", "State": 0, "Tau": 3.2}]
    experiment = {"detectors": {"Green": {"irf": list(np.random.rand(64)),
                                          "background": list(np.random.rand(64))}}}
    write_mle_container(src, tables, state_rows=states, experiment=experiment,
                        parameters={"model": "fit23"})
    audit(src.with_suffix(".pto"), "burst_mle", results)
    shutil.rmtree(tmp)


@case
def burst_fcs(results):
    from chisurf.plugins.burst.burst_fcs_correlator.core.export import write_fcs_container
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    tmp, src = fresh()
    write_container(src, bursts(), parameters={"min_photons": 60})
    write_fcs_container(src, pd.DataFrame({"Burst Index": [0, 1, 3],
                                           "td_mean__g-r": [0.5, 0.6, 0.4]}),
                        parameters={"n_casc": 20})
    audit(src.with_suffix(".pto"), "burst_fcs", results)
    shutil.rmtree(tmp)


@case
def burst_gs(results):
    from chisurf.plugins.burst.burst_gs import core as gs
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    tmp, src = fresh()
    write_container(src, bursts(), parameters={"min_photons": 60})
    gs.write_container(src, gs.analyse(gs.simulate_two_state(seed=3), n_states=2,
                                       decode_states=True),
                       parameters={"n_states": 2})
    audit(src.with_suffix(".pto"), "burst_gs", results)
    shutil.rmtree(tmp)


@case
def burst_ebfret(results):
    from chisurf.plugins.burst.burst_ebfret.core.analysis import analyse, write_container

    tmp, src = fresh()
    rng = np.random.default_rng(1)
    traces = [np.where(((rng.random(200) < .03).cumsum() % 2) == 0, .25, .75)
              + rng.normal(0, .05, 200) for _ in range(4)]
    write_container(src, analyse(traces, min_states=2, max_states=2),
                    parameters={"min_states": 2})
    audit(src.with_suffix(".pto"), "burst_ebfret", results)
    shutil.rmtree(tmp)


@case
def accurate_fret(results):
    from chisurf.plugins.burst.accurate_fret.core import calibrate, write_container
    from chisurf.plugins.burst.burst_selection.api.io import write_container as wc

    tmp, src = fresh()
    wc(src, bursts(), parameters={"min_photons": 60})
    rng = np.random.default_rng(0)
    n = 400
    E = np.concatenate([rng.normal(.3, .05, n // 2), rng.normal(.75, .05, n // 2)])
    res = calibrate(rng.poisson((1 - E) * 300).astype(float),
                    rng.poisson(E * 300).astype(float),
                    rng.poisson(250, n).astype(float))
    write_container(src, res, parameters={"donor_lifetime": 4.0})
    audit(src.with_suffix(".pto"), "accurate_fret", results)
    shutil.rmtree(tmp)


@case
def burst_background(results):
    from chisurf.plugins.burst.burst_background.view_model import BackgroundViewModel

    tmp, src = fresh()
    vm = BackgroundViewModel(show_channel_definition=False)
    vm.add_files([str(src)])
    vm.channels_provider = lambda: {"green": {"chs": [0, 1]}}
    vm.estimate()
    audit(src.with_suffix(".pto"), "burst_background", results)
    shutil.rmtree(tmp)


@case
def imaging_maps(results):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from chisurf.plugins.microscopy.img_pixel_nb.gui.view_model import NBViewModel

    tmp, src = fresh("Leica_SP5.ptu")
    vm = NBViewModel()
    vm.load_file(str(src))
    vm.compute()
    vm.write_container()
    audit(src.with_suffix(".pto"), "imaging_nb", results)
    shutil.rmtree(tmp)


@case
def img_drift(results):
    from chisurf.plugins.microscopy.img_drift import core as drift

    tmp, src = fresh("Leica_SP5.ptu")
    drift.write_container(src, np.array([[0., 0.], [1., -2.]]),
                          np.random.rand(2, 8, 8).astype(np.float32),
                          parameters={"upsample": 10})
    audit(src.with_suffix(".pto"), "img_drift", results)
    shutil.rmtree(tmp)


@case
def img_tracking(results):
    from chisurf.plugins.microscopy.img_tracking import core as tk

    tmp, src = fresh("Leica_SP5.ptu")
    try:
        result = tk.simulate() if hasattr(tk, "simulate") else None
    except Exception:
        result = None
    if result is None:
        results.append(("img_tracking", "(not exercised)", ["no simulator"]))
    else:
        tk.write_container(src, result, parameters={})
        audit(src.with_suffix(".pto"), "img_tracking", results)
    shutil.rmtree(tmp)


@case
def a_curve(results):
    from chisurf.core.data import DataCurve

    tmp, src = fresh()
    x = np.linspace(0, 25, 128)
    c = DataCurve(x=x, y=1000 * np.exp(-x / 4))
    c.name = "decay"
    c.save(str(src.with_suffix(".pto")))
    audit(src.with_suffix(".pto"), "curve", results)
    shutil.rmtree(tmp)


def main():
    results = []
    for fn in CASES:
        try:
            fn(results)
        except Exception as exc:
            results.append((fn.__name__, "(raised)", [f"{type(exc).__name__}: {exc}"]))
            traceback.print_exc(limit=2)

    print()
    print(f"{'writer':20} {'artifact':28} problems")
    print("-" * 88)
    bad = 0
    for label, name, problems in results:
        flag = "; ".join(problems) if problems else "ok"
        if problems:
            bad += 1
        print(f"{label:20} {name:28} {flag}")
    print("-" * 88)
    print(f"{len(results)} artifacts, {bad} with a broken or incomplete lineage")


main()
