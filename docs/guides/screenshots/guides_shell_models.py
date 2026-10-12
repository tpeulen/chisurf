"""Model-editor figures drawn by the emtk shell's Analysis dock.

Each grab puts the guide's data into a private shell session, adds the fit with the guide's model, sets
the state the caption describes, and writes just the Analysis dock::

    IMP_BFF_GPU=off python docs/guides/screenshots/guides_shell_models.py [name ...]

Names: ``03``, ``04``, ``05``, ``fcs``, ``tcspc``, ``pda``, ``pda3c``. Read every PNG afterwards.
"""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
os.chdir(pathlib.Path(__file__).resolve().parents[3])

import numpy as np  # noqa: E402
import shell_emtk as se  # noqa: E402

from chisurf.emtk.fit_docks import ANALYSIS_KEY  # noqa: E402

DECAY = "test/data/tcspc/decay_fit/Decay_577D.txt"
KRISTINE = "test/data/fcs/kristine/Kristine_with_error.cor"
SPC = pathlib.Path("test/data/tttr/BH/132/BH_SPC132.spc")
#: Window and dock box: the dock floats below the ribbon and is cropped out of the window.
WINDOW = (1500, 1500)


def _shell():
    return se.Shell(size=WINDOW)


def _editor(shell, name, height=1000, folds=None, width=640):
    """Open/close the panels in *folds* (title -> open), then write the Analysis dock as *name*."""
    editor = shell.data.editor
    for title, opened in (folds or {}).items():
        editor.form.folds[title] = opened
    shell.frames(3)
    return shell.crop_dock(ANALYSIS_KEY, name, box=(0, 125, width, height))


def _grab_03() -> None:
    """The SAW-nu and Ising-chain FRET editors on the IBH sample decay."""
    for model, name, height in (
        ("FRET: self-avoiding chain (SAW-ν)", "03_saw_nu_editor.png", 1335),
        ("FRET: Ising two-state chain", "03_ising_chain_editor.png", 1380),
    ):
        shell = _shell()
        row = shell.load(DECAY, "TCSPC", "TXT/CSV")
        shell.add_fit(model, row)
        print(shell.data.editor.visible_titles(), flush=True)
        _editor(shell, name, height)
        shell.close()


def _grab_04() -> None:
    """The FIDA model fitted to the BH_SPC132 green PCH (two species, bounds on)."""
    from chisurf.core.data import DataCurve
    from chisurf.plugins.pch.gui.client import PCHClient

    shell = _shell()
    result = PCHClient().compute(
        filename=str(SPC.resolve()), channels=[0, 8], bin_time_us=50.0,
        micro_time_min=0, micro_time_max=65535,
    )
    counts = np.asarray(result["hist_counts"], dtype=float)
    k = np.arange(counts.size, dtype=float)
    data = DataCurve(
        name="BH_SPC132 green 50 us", load_filename_on_init=False,
        x=k, y=counts / counts.sum(), ey=np.sqrt(np.maximum(counts, 1.0)) / counts.sum(),
    )
    row = shell.add_curve(data)
    shell.add_fit("FIDA", row)
    fit = shell.fit()
    model = fit.model
    fit.fit_range = (0, counts.size)
    start = {"q1": 0.5, "N1": 1.0, "q2": 5.0, "N2": 0.01}
    for p in model.parameters_all:
        if p.name[0] in "qN":
            p.bounds_on = True  # off by default: the fit then runs N negative
        if p.name in ("q3", "N3"):
            p.fixed = True
        if p.name in start:
            p.value = start[p.name]
    fit.run()
    print("FIDA chi2r", fit.chi2r, [(p.name, round(p.value, 4)) for p in model.parameters_all], flush=True)
    shell.refresh()
    print(shell.data.editor.visible_titles(), flush=True)
    _editor(shell, "04_fida_editor.png", 480, width=800)
    shell.close()


def _grab_05() -> None:
    """The MDF FCS model fitted to the Kristine curve (lags > 1 us), Optics and Outputs open."""
    from chisurf.core.data import DataCurve

    shell = _shell()
    a = np.loadtxt(KRISTINE)
    sel = a[:, 0] > 1e-3
    data = DataCurve(
        name="Kristine_with_error.cor", load_filename_on_init=False,
        x=a[sel, 0], y=a[sel, 1], ey=a[sel, 3],
    )
    row = shell.add_curve(data)
    shell.add_fit("FCS MDF (Gauss-Lorentz)", row)
    fit = shell.fit()
    fit.fit_range = (0, int(sel.sum()))
    fit.run()
    print("MDF chi2r", fit.chi2r, [(p.name, round(p.value, 4)) for p in fit.model.parameters_all], flush=True)
    shell.refresh()
    titles = shell.data.editor.visible_titles()
    print(titles, flush=True)
    _editor(shell, "05_mdf_editor.png", 690,
            {t: True for t in titles if any(w in t for w in ("Outputs", "Optics"))})
    shell.close()


def _grab_fcs() -> None:
    """The composable FCS editor on the Kristine curve."""
    shell = _shell()
    row = shell.load(KRISTINE, "FCS", "Seidel Kristine")
    shell.add_fit("FCS (general: diffusion + bunching/anticorr)", row)
    print(shell.data.editor.visible_titles(), flush=True)
    _editor(shell, "fcs_model_editor.png", 520)
    shell.close()


def _grab_tcspc() -> None:
    """The TCSPC multi-exponential lifetime editor with the prompt as IRF."""
    shell = _shell()
    shell.load("test/data/tcspc/decay_fit/Prompt.txt", "TCSPC", "TXT/CSV")
    row = shell.load(DECAY, "TCSPC", "TXT/CSV")
    shell.add_fit("Lifetime", row)
    print(shell.data.editor.visible_titles(), flush=True)
    _editor(shell, "tcspc_lifetime_editor.png", 960)
    shell.close()


def _pda_curve():
    from chisurf.core.data import DataCurve
    import chisurf.core.fluorescence.tcspc as tcspc
    from chisurf.core.math import special as stats

    nmax, nmin = 60, 5
    n = np.arange(nmax + 1)
    ps = stats.poisson.pmf(n, mu=20.0).astype(float)
    ps /= ps.sum()
    s1s2 = np.zeros((nmax + 1, nmax + 1), dtype=float)
    for N in range(nmin, nmax + 1):
        g = np.arange(N + 1)
        s1s2[g, N - g] += ps[N] * stats.binom.pmf(g, N, 0.6) * 1000.0
    ny, nx = s1s2.shape
    rr, cc = np.indices((ny, nx))
    y = s1s2.ravel(order="C")
    pda = {
        "maximum_number_of_photons": nmax, "minimum_number_of_photons": nmin,
        "minimum_time_window_length": 2e-3, "segmentation": "time-bins", "observation_time": 2e-3,
        "channels": ([0], [1]), "s1s2": s1s2, "ps": ps,
        "row_indices": rr.ravel().tolist(), "col_indices": cc.ravel().tolist(),
        "ndim": 2, "shape": (ny, nx), "size": int(y.size), "tttr_indices": None,
    }
    return DataCurve(name="synthetic-pda", load_filename_on_init=False, pda=pda, y=y,
                     x=np.arange(y.size), ey=tcspc.counting_noise(y))


def _grab_pda() -> None:
    """The PDA Gaussian-distance editor on a synthetic S1S2 histogram."""
    import chisurf
    from chisurf.core.experiments.bootstrap import ensure_experiments_registered

    shell = _shell()
    ensure_experiments_registered(allow_widgets=False)
    reader = next(r for r in chisurf.experiment["PDA"].readers if str(r.name) == "PTU/HT3/SPC")
    curve = _pda_curve()
    curve.experiment = reader.experiment
    curve.setup = reader
    row = shell.add_curve(curve)
    shell.add_fit("PDA2c-Gaussian-distance", row)
    print(shell.data.editor.visible_titles(), flush=True)
    _editor(shell, "pda_model_editor.png", 455, width=820)
    shell.close()


def _grab_pda3c() -> None:
    """The PDA3c exchange panel: three species on a linear 1-2-3 chain (k13, k31 zero)."""
    import chisurf
    from chisurf.core.experiments.bootstrap import ensure_experiments_registered
    from chisurf.core.experiments.pda3c import Pda3cSimulatorReader

    shell = _shell()
    ensure_experiments_registered(allow_widgets=False)
    data = Pda3cSimulatorReader(n_bursts=200, seed=3).read()[0]
    row = shell.add_curve(data)
    shell.add_fit("PDA3c (three-colour)", row)
    model = shell.fit().model
    model.species.append(r_gr=68.0, r_bg=62.0, r_br=80.0)
    model.species.append(r_gr=78.0, r_bg=72.0, r_br=90.0)
    model.dynamic = True
    model.rate_matrix = np.array([[0.0, 120.0, 0.0], [80.0, 0.0, 300.0], [0.0, 90.0, 0.0]])
    model.find_parameters()
    shell.refresh()
    titles = shell.data.editor.visible_titles()
    print(titles, flush=True)
    folds = {t: ("Exchange" in t) for t in titles if "Exchange" in t or "Distance" in t}
    _editor(shell, "pda3c_exchange.png", 600, folds)
    shell.close()


GRABS = {"03": _grab_03, "04": _grab_04, "05": _grab_05, "fcs": _grab_fcs, "tcspc": _grab_tcspc,
         "pda": _grab_pda, "pda3c": _grab_pda3c}

if __name__ == "__main__":
    for key in sys.argv[1:] or GRABS:
        GRABS[key]()
    os._exit(0)
