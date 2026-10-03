"""Capture populated and empty screenshots of the ALEX Suite EMTK port.

Usage:
    python okf/plugins/emtk-ports/alex_suite/scripts/capture_emtk.py <out_dir>
"""

from __future__ import annotations

import pathlib
import sys
import numpy as np

sys.path.insert(0, ".")
import test.gui.emtk_port_parity as parity
from chisurf.plugins.burst.alex_suite.gui.app import make_app
from chisurf.plugins.emtk_test_input import Driver


def setup_populated_alternation(app):
    state = app.suite_gui.alternation_state
    state.donor_text = "0"
    state.acceptor_text = "1"
    state.period = 8000
    state.windows = {"green": [300, 3700], "red": [4300, 7700]}
    state.status_text = "Gates 300–3700 and 4300–7700 published as \u201cALEX Suite (auto)\u201d."
    state.detail_text = "Detected period: 8000 (confidence: 420.5)\nDonor excitation (green): 300–3700\nAcceptor excitation (red): 4300–7700"
    state.detail_note = "Contrast ratio 0.08: clean separation between excitation periods."

    # Realistic folded phase distribution
    centres = np.linspace(0, 8000, 100)
    donor = np.exp(-0.5 * ((centres - 2000) / 700) ** 2) * 5000 + 150
    acceptor = np.exp(-0.5 * ((centres - 6000) / 700) ** 2) * 4500 + 120
    state.phase_hist = {
        "centres": centres,
        "donor": donor,
        "acceptor": acceptor,
        "period": 8000,
    }


def _burst_table(n, e_true, *, s_true=0.5, size=200, seed=0):
    """Synthesise a burst table whose bursts have a known E and S (as test_api's)."""
    import numpy as np

    rng = np.random.default_rng(seed)
    total = rng.poisson(size, n).astype(float) + 20.0
    green = total * s_true
    i_da = rng.binomial(green.astype(int), e_true).astype(float)
    return {
        "Number of Photons (green)": green - i_da,
        "Number of Photons (red)": i_da,
        "Number of Photons (yellow)": total - green,
        "Duration (ms)": np.full(n, 1.0),
    }


def _two_population_table(n, frac_high, *, low=0.25, high=0.65, seed=0):
    import numpy as np

    n_high = int(round(n * frac_high))
    a = _burst_table(n - n_high, low, seed=seed)
    b = _burst_table(n_high, high, seed=seed + 1000)
    return {key: np.concatenate([a[key], b[key]]) for key in a}


def _write_burst_table(path, table):
    """Write a delimited burst table read_burst_table accepts (header first line)."""
    import numpy as np

    keys = list(table)
    lines = ["\t".join(keys)]
    rows = np.column_stack([table[k] for k in keys])
    lines += ["\t".join(f"{v:.10g}" for v in row) for row in rows]
    pathlib.Path(path).write_text("\n".join(lines) + "\n")


def setup_populated_titration(app, tmp_dir: pathlib.Path):
    model = app.suite_gui.titration_state.model

    # Synthesize titration data files
    concs = [0.0, 5.0, 15.0, 50.0, 150.0, 500.0]
    fracs = [0.10, 0.22, 0.45, 0.72, 0.88, 0.94]
    files = []
    for c, f in zip(concs, fracs):
        t = _two_population_table(500, f, low=0.25, high=0.70, seed=int(c * 10))
        p = tmp_dir / f"titration_{c:g}nM.bur"
        _write_burst_table(p, t)
        files.append(str(p))

    model.add_files(files)
    for i, c in enumerate(concs):
        model.update_series_cell(i, "concentration", f"{c:g}")
    model.run()


def setup_populated_export(app, tmp_dir: pathlib.Path):
    gui = app.suite_gui.export_gui
    state = app.suite_gui.export_state

    p = tmp_dir / "alex_experiment_sample1.bur"
    t = _burst_table(1000, 0.48, s_true=0.52, seed=42)
    _write_burst_table(p, t)

    state.set_burst_files([p])
    gui.selected_index = 0
    gui.sample_text = "dsDNA 15bp Cy3B/ATTO647N"
    gui.buffer_text = "PBS + 50 mM NaCl, pH 7.4"
    gui.parts["metadata"] = True
    gui.parts["e_histogram"] = True
    gui.parts["s_histogram"] = True
    gui.parts["histogram_2d"] = True
    gui.parts["original_bursts"] = True


def main():
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("okf/plugins/emtk-ports/alex_suite")
    out.mkdir(parents=True, exist_ok=True)
    scripts_dir = out / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    tmp_dir = out / ".tmp_data"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    sizes = ((1200, 800), (800, 600))

    # 1. Empty alternation
    for size in sizes:
        tag = f"{size[0]}x{size[1]}"
        app = make_app()
        app.suite_gui.selected_tab = "alternation"
        drv = Driver(app, size)
        drv.draw(2)
        parity.emtk_screenshot(app, out / f"after_alternation_empty_{tag}.png", size)

    # 2. Populated alternation
    for size in sizes:
        tag = f"{size[0]}x{size[1]}"
        app = make_app()
        app.suite_gui.selected_tab = "alternation"
        setup_populated_alternation(app)
        drv = Driver(app, size)
        drv.draw(2)
        parity.emtk_screenshot(app, out / f"after_alternation_populated_{tag}.png", size)
        # Use alternation as default after screenshot
        parity.emtk_screenshot(app, out / f"after_{tag}.png", size)

    # 3. Empty titration
    for size in sizes:
        tag = f"{size[0]}x{size[1]}"
        app = make_app()
        app.suite_gui.selected_tab = "titration"
        drv = Driver(app, size)
        drv.draw(2)
        parity.emtk_screenshot(app, out / f"after_titration_empty_{tag}.png", size)

    # 4. Populated titration
    for size in sizes:
        tag = f"{size[0]}x{size[1]}"
        app = make_app()
        app.suite_gui.selected_tab = "titration"
        setup_populated_titration(app, tmp_dir)
        drv = Driver(app, size)
        drv.draw(2)
        parity.emtk_screenshot(app, out / f"after_titration_populated_{tag}.png", size)

    # 5. Empty export
    for size in sizes:
        tag = f"{size[0]}x{size[1]}"
        app = make_app()
        app.suite_gui.selected_tab = "export"
        drv = Driver(app, size)
        drv.draw(2)
        parity.emtk_screenshot(app, out / f"after_export_empty_{tag}.png", size)

    # 6. Populated export
    for size in sizes:
        tag = f"{size[0]}x{size[1]}"
        app = make_app()
        app.suite_gui.selected_tab = "export"
        setup_populated_export(app, tmp_dir)
        drv = Driver(app, size)
        drv.draw(2)
        parity.emtk_screenshot(app, out / f"after_export_populated_{tag}.png", size)

    print("ALEX Suite screenshots captured successfully.")


if __name__ == "__main__":
    main()
