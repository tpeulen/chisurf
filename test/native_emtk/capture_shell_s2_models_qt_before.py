"""Capture the before-half of W9 S2's model sections: the Qt model editor of each kind of model.

The first S2 inventory (``capture_shell_s2_qt_before.py``) held one model, the general FCS
model, so the parity test could not see the curve pickers (IRF, background, linearisation
table) or the nine ``custom`` sections. This script drives the Qt shell into one realistic
state per kind and writes the :func:`migration_parity.control_inventory` of each fit's
model editor (``build_model_editor``, the widget the Analysis dock shows), plus the Read
data dock with the PDA reader's settings form:

* TCSPC ``Decay_577D.txt`` (TXT/CSV) with ``Prompt.txt`` attached as IRF and background:
  *Lifetime* (curve pickers, anisotropy diagnostics), *FRET: Gaussian distances* (κ²
  controls), *Lifetime mixture* (fit mixer), *Lifetime: MaxEnt*
  (L-curve), *FRET: Structure fit* (path list);
* FCS Kristine: *FCS (kinetics)* (rate matrix);
* PDA (a synthetic S1S2 histogram): *PDA2c-discrete* (scalar table),
  *PDA2c-dynamic-N-state* (rate matrix and scalar table);
* the Global Dataset: *Global fit* holding the Lifetime fit (global parameter table);
* Modelling ``148l.pdb``: *ProteinMC* (background run).

Not a test (the Qt shell takes a minute to start). Run from the repository root::

    S=$(mktemp -d); QT_QPA_PLATFORM=offscreen CHISURF_SETTINGS_DIR=$S/settings HOME=$S/home \\
        python -u test/native_emtk/capture_shell_s2_models_qt_before.py

PNGs and ``qt_models_inventory.json`` go to ``$CHISURF_S2_BEFORE_DIR`` (``renders/w9_s2``);
``test/native_emtk/shell_s2_models_qt_inventory.json`` is that inventory.
"""

from __future__ import annotations

import faulthandler
import json
import os
import socket
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TCSPC = REPO / "test" / "data" / "tcspc" / "decay_fit"
KRISTINE = REPO / "test" / "data" / "fcs" / "kristine" / "Kristine_with_error.cor"
PDB = REPO / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"

#: (key, experiment, model) of every fit whose editor is captured, in the order they are made.
FITS = (
    ("tcspc_lifetime", "TCSPC", "Lifetime"),
    ("tcspc_fret_gaussian", "TCSPC", "FRET: Gaussian distances"),
    ("tcspc_mixture", "TCSPC", "Lifetime mixture"),
    ("tcspc_maxent_lifetime", "TCSPC", "Lifetime: MaxEnt"),
    ("fret_structure", "TCSPC", "FRET: Structure fit"),
    ("fcs_kinetics", "FCS", "FCS (kinetics)"),
    ("pda_discrete", "PDA", "PDA2c-discrete"),
    ("pda_dynamic_n", "PDA", "PDA2c-dynamic-N-state"),
    ("global_fit", "Global", "Global fit"),
    ("proteinmc", "Modelling", "ProteinMC"),
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def make_pda_curve():
    """A synthetic two-colour PDA dataset (an S1S2 histogram of 60 photons at most), the PDA reader's shape."""
    import numpy as np
    from scipy import stats

    import chisurf.core.fluorescence.tcspc as tcspc
    from chisurf.core.data import DataCurve

    nmax, nmin = 60, 5
    n = np.arange(nmax + 1)
    ps = stats.poisson.pmf(n, mu=20.0).astype(float)
    ps /= ps.sum()
    s1s2 = np.zeros((nmax + 1, nmax + 1), dtype=float)
    for count in range(nmin, nmax + 1):
        g = np.arange(count + 1)
        s1s2[g, count - g] += ps[count] * stats.binom.pmf(g, count, 0.6) * 1000.0
    ny, nx = s1s2.shape
    rr, cc = np.indices((ny, nx))
    y = s1s2.ravel(order="C")
    pda = {
        "maximum_number_of_photons": nmax,
        "minimum_number_of_photons": nmin,
        "minimum_time_window_length": 2e-3,
        "segmentation": "time-bins",
        "observation_time": 2e-3,
        "channels": ([0], [1]),
        "s1s2": s1s2,
        "ps": ps,
        "row_indices": rr.ravel().tolist(),
        "col_indices": cc.ravel().tolist(),
        "ndim": 2,
        "shape": (ny, nx),
        "size": int(y.size),
        "tttr_indices": None,
    }
    return DataCurve(
        name="synthetic-pda",
        load_filename_on_init=False,
        pda=pda,
        y=y,
        x=np.arange(y.size),
        ey=tcspc.counting_noise(y),
    )


def main() -> None:
    """Drive the Qt shell through every model kind and write the PNGs and the inventory."""
    faulthandler.dump_traceback_later(3600, exit=True)
    sys.path.insert(0, str(REPO / "test" / "gui"))
    from mmfdb.security import credentials

    credentials.store_session_token = lambda *args, **kwargs: False
    credentials.load_session_token = lambda *args, **kwargs: None

    from migration_parity import control_inventory
    from qtpy import QtWidgets

    import chisurf
    import chisurf.gui
    from chisurf.core import settings

    settings.cs_settings.setdefault("mmfdb", {}).update(
        cmd_port=_free_port(), pub_port=_free_port()
    )
    app = chisurf.gui.get_app()
    gui = chisurf.cs
    gui.resize(1440, 1100)

    def pump(seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)

    pump(2)
    wizard = QtWidgets.QApplication.activeModalWidget()
    if wizard is not None:
        wizard.reject()
        pump(0.5)

    # The file and sample dialogs are modal: answer them without showing them.
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "show_sample_picker_dialog", None) is not None:
            try:
                module.show_sample_picker_dialog = lambda *args, **kwargs: None
            except Exception:  # noqa: BLE001 - a read-only module attribute
                pass

    def choose(combo, text: str) -> None:
        combo.setCurrentIndex([combo.itemText(i) for i in range(combo.count())].index(text))
        pump(0.5)

    def load(experiment: str, setup: str, path: Path) -> int:
        choose(gui.comboBox_experimentSelect, experiment)
        choose(gui.comboBox_setupSelect, setup)
        before = len(chisurf.imported_datasets)
        # What + Data dispatches once the reader has its file (the file dialog is not shown).
        chisurf.core.actions.dispatch(
            name="dataset.add",
            payload={"filename": path.as_posix(), "experiment_reader": gui.current_setup},
        )
        pump(3)
        assert len(chisurf.imported_datasets) > before, f"{path.name} was not read"
        return len(chisurf.imported_datasets) - 1

    def add_fit(dataset_index: int, model: str):
        selector = gui.dataset_selector
        selector.setCurrentIndex(selector.model().index(dataset_index, 0))
        pump(0.5)
        choose(gui.comboBox_Model, model)
        before = len(chisurf.fits)
        gui.toolButton.click()
        pump(6)
        assert len(chisurf.fits) == before + 1, f"the {model} fit was not added"
        return chisurf.fits[-1]

    out = Path(os.environ.get("CHISURF_S2_BEFORE_DIR", REPO / "renders" / "w9_s2"))
    out.mkdir(parents=True, exist_ok=True)
    inventory: dict = {}

    def write() -> None:
        payload = {
            "_comment": (
                "Before-half of W9 S2's model sections: control_inventory (test/gui/migration_parity.py) "
                "of the Qt model editor of each model kind and of the Read data dock with the PDA "
                "PTU/HT3/SPC reader, made by test/native_emtk/capture_shell_s2_models_qt_before.py "
                f"on {time.strftime('%Y-%m-%d')} before the emtk sections were drawn."
            ),
            "models": {k: v for k, v in inventory.items() if not k.startswith("read:")},
            "readers": {k[5:]: v for k, v in inventory.items() if k.startswith("read:")},
        }
        (out / "qt_models_inventory.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")

    def grab_reader(key: str) -> None:
        dock = gui.dockWidgetReadData
        dock.show()
        dock.raise_()
        pump(0.5)
        dock.grab().save(str(out / f"qt_read_{key}.png"))
        inventory[f"read:{key}"] = control_inventory(dock)
        write()

    def grab_editor(key: str, fit) -> None:
        from chisurf.gui.widgets.models.model_editor import build_model_editor

        editor = build_model_editor(fit.model)
        editor.resize(560, max(editor.sizeHint().height(), 900))
        editor.show()
        pump(1)
        editor.grab().save(str(out / f"qt_model_{key}.png"))
        inventory[key] = control_inventory(editor)
        write()

    # ── TCSPC: a decay and its prompt (IRF and background) ──────────────────
    irf = load("TCSPC", "TXT/CSV", TCSPC / "Prompt.txt")
    decay = load("TCSPC", "TXT/CSV", TCSPC / "Decay_577D.txt")
    irf_name = str(chisurf.imported_datasets[irf].name)

    def attach_curves(fit) -> None:
        """The prompt into each IRF and background picker the model's editor declares, as a pick sends it."""
        from chisurf.core import dataspec as vs

        index = list(chisurf.fits).index(fit)
        for section in fit.model.view_spec().flat_sections():
            if not isinstance(section, vs.CurveInputSection) or section.label not in ("IRF", "Background"):
                continue
            payload = dict(section.action_fixed or {})
            payload.update({section.index_key: irf, section.name_key: irf_name, "fit_index": index})
            chisurf.core.actions.dispatch(name=section.select_action, payload=payload)
        pump(2)

    fits = {}
    for key, experiment, model in FITS[:5]:
        fit = add_fit(decay, model)
        fits[key] = fit
        if key != "fret_structure":
            attach_curves(fit)
        # The mixture is left without a source: mixing the Lifetime fit fails in the model
        # itself (okf/references/known-issues.md, "Lifetime mixture"); its controls are all there.
        grab_editor(key, fit)

    # ── FCS kinetics ─────────────────────────────────────────────────────────
    kristine = load("FCS", "Seidel Kristine", KRISTINE)
    grab_editor("fcs_kinetics", add_fit(kristine, "FCS (kinetics)"))

    # ── PDA: the reader's form, then a synthetic S1S2 dataset ────────────────
    choose(gui.comboBox_experimentSelect, "PDA")
    choose(gui.comboBox_setupSelect, "PTU/HT3/SPC")
    pump(1)
    grab_reader("pda_ptu")
    pda_reader = next(r for r in chisurf.experiment["PDA"].readers if str(r.name) == "PTU/HT3/SPC")
    curve = make_pda_curve()
    curve.experiment = pda_reader.experiment
    curve.setup = pda_reader
    chisurf.imported_datasets.append(curve)
    try:
        gui.dataset_selector.update()
    except Exception:  # noqa: BLE001 - the selector refreshes on the next add otherwise
        pass
    pump(1)
    pda = len(chisurf.imported_datasets) - 1
    grab_editor("pda_discrete", add_fit(pda, "PDA2c-discrete"))
    grab_editor("pda_dynamic_n", add_fit(pda, "PDA2c-dynamic-N-state"))

    # ── the global fit, holding the Lifetime fit ─────────────────────────────
    global_fit = add_fit(0, "Global fit")
    model = global_fit.model
    model.selected_candidate_fit = str(fits["tcspc_lifetime"].name)
    try:
        model.add_selected_fit()
    except Exception as error:  # noqa: BLE001 - the editor is still captured
        print(f"global fit: {error}")
    pump(1)
    grab_editor("global_fit", global_fit)

    # ── ProteinMC on T4 lysozyme ─────────────────────────────────────────────
    try:
        structure = load("Modelling", "StructureReader", PDB)
        grab_editor("proteinmc", add_fit(structure, "ProteinMC"))
    except Exception as error:  # noqa: BLE001 - recorded, the rest is still written
        print(f"proteinmc: {error}")

    write()
    print(f"wrote {out}: {sorted(inventory)}")
    os._exit(0)


if __name__ == "__main__":
    main()
