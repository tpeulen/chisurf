"""The release scenario: one measurement, driven through the real app from photons to a legacy folder.

A headless worker starts the ChiSurf main window and walks the burst workflow on the shipped
Burst Selection demo (twelve planted bursts, so every count below is known in advance):

    start app -> load the demo ``.pto`` -> burst selection -> MLE -> H2MM -> sub-ensemble decay
    -> burst-wise FCS -> run picker -> sampling -> Chain-diagnostics page -> autosave
    -> reload -> "Open in ndX" -> legacy export

Every step asserts something a user could check: a row count, the analyses inside the container
(read back through :class:`chisurf.core.fio.pto.Measurement`), ``lineage()`` reaching the photon
stream, a file on disk. The worker runs once in its own process with scratch settings, home, temp
and RPC ports -- it never touches the user's ``~/.chisurf``, keychain or a running ChiSurf -- and
writes one JSON record per step plus three screenshots to ``renders/e2e/release_scenario``. Each
step is then its own test here, so a step the product cannot do yet is a strict ``xfail`` with the
reason, not a stop for the rest of the walk. Gaps are recorded in
``okf/references/known-issues.md``.

Run: ``QT_QPA_PLATFORM=offscreen python -m pytest -q -p no:cacheprovider test/e2e/test_release_scenario.py``.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "renders" / "e2e" / "release_scenario"
RESULT = OUT / "result.json"

#: Steps whose product half is missing. Strict: the day one starts to pass, the test says so.
XFAIL = {
    "run_picker": (
        "MLE, H2MM and burst-wise FCS write their tables at the container's top level "
        "('mle green', 'h2mm', 'burst fcs'), not as runs of their own, so run_rows_for "
        "folds them into one '(top level)' row: the picker lists 2 runs, not 5 "
        "(known-issues: 'The run picker cannot tell the burst analyses apart')."
    ),
}

STEPS = [
    "start_app",
    "load_demo_pto",
    "burst_selection",
    "mle",
    "h2mm",
    "sub_ensemble_decay",
    "burst_fcs",
    "run_picker",
    "sampling",
    "diagnostics_page",
    "autosave",
    "reload",
    "open_in_ndx",
    "legacy_export",
]

#: Sampling small enough to be quick, long enough for the diagnostics page (>= 8 draws).
SAMPLING = {"steps": 60, "n_runs": 2}


# --------------------------------------------------------------------------------------------- the worker
class Blocked(RuntimeError):
    """A step that cannot run because an earlier one failed."""


def _free_port() -> int:
    """Return a TCP port nobody listens on now."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Scenario:
    """The walk, one method per step; ``state`` carries what later steps need."""

    def __init__(self, scratch: Path) -> None:
        self.scratch = scratch
        self.state: dict = {}
        self.results: dict = {}

    # -- plumbing ------------------------------------------------------------------------------------- #
    def pump(self, seconds: float) -> None:
        """Let Qt deliver events (timers, queued signals) for *seconds*."""
        app = self.state["app"]
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)

    def wait_for(self, predicate, timeout: float, what: str):
        """Pump until *predicate* returns something truthy; fail naming *what* otherwise."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = predicate()
            if value:
                return value
            self.pump(0.1)
        raise AssertionError(f"timed out after {timeout:g}s waiting for {what}")

    def need(self, *keys: str) -> None:
        """Raise :class:`Blocked` unless earlier steps left every one of *keys*."""
        missing = [k for k in keys if k not in self.state]
        if missing:
            raise Blocked(f"blocked: needs {', '.join(missing)} from an earlier step")

    def grab(self, name: str, widget=None) -> str:
        """Save a PNG of *widget* (default: the main window)."""
        widget = widget or self.state["gui"]
        path = OUT / f"{name}.png"
        if not widget.grab().save(str(path)):
            raise AssertionError(f"could not save {path}")
        return str(path)

    def write(self) -> None:
        """Write the per-step record (after every step, so a crash leaves what ran)."""
        RESULT.write_text(json.dumps(self.results, indent=2, default=str), encoding="utf-8")

    def run(self) -> None:
        """Walk every step; record its outcome; never stop early."""
        for step in STEPS:
            start = time.monotonic()
            record: dict = {"status": "running"}
            self.results[step] = record
            self.write()
            try:
                record["observed"] = getattr(self, step)()
                record["status"] = "passed"
            except Blocked as exc:
                record.update(status="blocked", error=str(exc))
            except BaseException as exc:  # noqa: BLE001 - every outcome is recorded, none ends the walk
                record.update(
                    status="failed",
                    error=f"{type(exc).__name__}: {exc}",
                    traceback=traceback.format_exc(),
                )
            record["seconds"] = round(time.monotonic() - start, 2)
            self.write()

    # -- the steps ------------------------------------------------------------------------------------ #
    def start_app(self):
        """The main window comes up, its post-show services (autosave among them) run."""
        # The OS keystore is the user's: startup's autologin would write a session token there.
        from mmfdb.security import credentials

        credentials.store_session_token = lambda *args, **kwargs: False
        credentials.load_session_token = lambda *args, **kwargs: None

        import chisurf
        import chisurf.gui
        from chisurf.core import settings

        # A private RPC endpoint: a ChiSurf already running on the stock port would be adopted
        # and every fit call would go to *its* session (see the main-window driver harness).
        settings.cs_settings.setdefault("mmfdb", {}).update(
            cmd_port=_free_port(), pub_port=_free_port()
        )
        settings.cs_settings.setdefault("project", {}).setdefault("autosave", {}).update(
            enabled=True, interval_s=1
        )
        from qtpy.QtWidgets import QApplication

        app = chisurf.gui.get_app()
        gui = chisurf.cs
        assert gui is not None, "get_app built no main window"
        self.state.update(app=app, gui=gui, cs=chisurf)
        gui.resize(1440, 900)
        self.wait_for(lambda: hasattr(gui, "_autosave_timer"), 120, "the post-show services")
        chisurf.working_path = str(self.scratch / "work")
        (self.scratch / "work").mkdir(exist_ok=True)
        observed = {"autosave_interval_ms": gui._autosave_timer.interval()}
        # A first start greets the user with the welcome wizard; the user closes it.
        wizard = QApplication.activeModalWidget()
        if wizard is not None:
            observed["closed_on_start"] = type(wizard).__name__
            wizard.reject()
            self.pump(0.5)
        assert QApplication.activeModalWidget() is None, "a modal dialog stayed open after start"
        assert observed["autosave_interval_ms"] == 1000
        return observed

    def load_demo_pto(self):
        """The demo photon stream, packed into its measurement container; the vendor file goes."""
        from chisurf.core.fio.pto import Measurement
        from chisurf.plugins.burst.burst_selection import demo

        spc = demo.make_demo(self.scratch / "data")
        with Measurement.create(spc, title="Burst Selection demo") as m:
            pto = m.path
        spc.unlink()  # from here on the container is the only copy of the photons
        spc.with_suffix(".json").unlink()
        with Measurement.open(pto) as m:
            kinds = {str(o.name): o.kind for o in m.artifacts()}
        assert kinds.get("bs_demo.spc") == "tttr_photon_stream", kinds
        self.state.update(pto=Path(pto), demo=demo)
        return {"container": str(pto), "objects": kinds}

    def burst_selection(self):
        """The search finds every planted burst and writes them as a run of the container."""
        self.need("pto")
        from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

        demo, pto = self.state["demo"], self.state["pto"]
        model = BurstSelectionModel()
        model.set_setup({**demo.SETUP, "setup_name": ""})
        assert model.add_paths([pto]) == 1
        assert model.prepare_run() is None, model.blocked_reason()
        model.run()
        assert model.n_bursts == demo.N_BURSTS, f"{model.n_bursts} bursts, {demo.N_BURSTS} planted"
        rows = model.run_rows()
        assert len(rows) == 1 and rows[0]["rows"] == demo.N_BURSTS, rows
        model.select_run(rows[0])
        assert not list(pto.parent.glob("*#*")), "a .pto input must not get a legacy folder"
        self.state.update(selection=model, run=rows[0]["run_name"])
        return {"bursts": model.n_bursts, "run": rows[0]["run_name"]}

    def mle(self):
        """Burst-wise lifetimes of the picked run, written into the container."""
        self.need("run")
        from chisurf.plugins.burst.burst_mle_analysis.gui.model import MleViewModel

        demo, pto = self.state["demo"], self.state["pto"]
        model = MleViewModel()
        model.set_setup({**demo.SETUP})
        assert model.add_files([pto]) == 1
        model.select_run(model.run_rows()[-1])
        assert model.n_bursts == demo.N_BURSTS
        for detector in model.session.detectors:
            model.session.current_detector = detector
            model.session.auto_extract()
        model.run_batch()
        assert len(model.burst_results) == 2 * demo.N_BURSTS, model.status_text  # green and red
        assert model.export_results() >= 1, model.status_text
        tables = self._tables(operation="burst_lifetime_fitting")
        assert {"mle green", "mle red"} <= set(tables), tables
        assert all(rows == demo.N_BURSTS for rows in tables.values()), tables
        return {"status": model.status_text, "tables": tables}

    def h2mm(self):
        """Photon-by-photon HMM of the run; the result table lands in the container."""
        self.need("run")
        from chisurf.plugins.burst.burst_h2mm.gui.model import H2mmViewModel

        demo, pto = self.state["demo"], self.state["pto"]
        model = H2mmViewModel()
        model.set_setup({**demo.SETUP})
        model.donor, model.acceptor = "green", "red"
        model.data_folder = str(pto)
        model.select_run(model.run_rows()[-1])
        model.max_states = 2
        assert model.can_run() == "", model.can_run()
        model.compute()
        assert model.result is not None and model.result.n_bursts == demo.N_BURSTS, model.status_text
        tables = self._tables(operation="photon_hmm")
        assert tables and all(rows == demo.N_BURSTS for rows in tables.values()), tables
        return {"status": model.status_text, "tables": tables}

    def sub_ensemble_decay(self):
        """*Decay from selected bursts*: a decay beside the run, and a dataset in the main window."""
        self.need("selection", "gui")
        cs = self.state["cs"]
        model = self.state["selection"]
        model.decay_bins = 256
        before = len(cs.imported_datasets)
        verdict = model.write_decay()
        assert verdict.startswith("Decay of 12 bursts"), verdict
        assert "registered as a dataset" in verdict, verdict
        assert len(cs.imported_datasets) == before + 1
        dataset = cs.imported_datasets[-1]
        tables = self._tables(operation="tcspc_histogram_computation")
        assert tables == {f"{self.state['run']}/sub-ensemble decay": 256}, tables
        self.state["decay_dataset"] = len(cs.imported_datasets) - 1
        return {"verdict": verdict, "dataset": dataset.name, "counts": float(dataset.y.sum())}

    def burst_fcs(self):
        """One correlation curve per burst of the run, written into the container."""
        self.need("run")
        from chisurf.plugins.burst.burst_fcs_correlator.gui.controller import BurstFcsController

        demo, pto = self.state["demo"], self.state["pto"]
        ctrl = BurstFcsController()
        try:
            ctrl.apply_pairs(json.dumps([{"pair_name": "ACF_green", "chs_a": [0], "chs_b": [0]}]))
            ctrl.add_files([str(pto)])
            ctrl.select_run(ctrl.run_rows()[-1])
            ctrl._on_run()  # the Run button's handler
            end = time.monotonic() + 120
            while ctrl._future is not None and time.monotonic() < end:
                time.sleep(0.05)
                ctrl.poll()
            assert ctrl._future is None, "burst-wise FCS did not finish"
            assert len(ctrl._curves) == demo.N_BURSTS, ctrl.status
            status = ctrl.status
        finally:
            ctrl.close()
        tables = self._tables(name="burst fcs")
        assert tables, "no 'burst fcs' table in the container"
        return {"status": status, "tables": tables}

    def run_picker(self):
        """Every analysis is a run the picker lists; each traces back to the photons."""
        self.need("run")
        from chisurf.core.fio.pto import Measurement
        from chisurf.plugins.core.pto_inspector.core import run_rows_for

        pto = self.state["pto"]
        lineage = {}
        with Measurement.open(pto) as m:
            for obj in m.artifacts():
                if obj.kind in ("readme", "tttr_photon_stream"):
                    continue
                chain = m.lineage(obj.uid)
                lineage[str(obj.name)] = [step["name"] for step in chain]
                assert chain[-1]["name"] == "bs_demo.spc", (obj.name, chain)
        rows = run_rows_for(pto, operation="")
        observed = {
            "rows": [(r["run"], r["operation"], r["rows"]) for r in rows],
            "lineage": lineage,
        }
        self.results["run_picker"]["observed"] = observed
        operations = {r["operation"] for r in rows}
        assert len(rows) == 5, f"the picker lists {len(rows)} runs: {observed['rows']}"
        assert operations >= {"burst_selection", "burst_lifetime_fitting", "photon_hmm"}, operations
        return observed

    def sampling(self):
        """Fit the sub-ensemble decay in the main window, then press Sampling."""
        self.need("decay_dataset")
        from qtpy import QtCore
        from qtpy.QtTest import QTest

        import chisurf.gui.widgets
        from chisurf.core import settings
        from chisurf.gui.widgets.fitting import FitSubWindow
        from chisurf.gui.widgets.fitting.fit_controller import FittingControllerWidget

        cs, gui = self.state["cs"], self.state["gui"]
        cs.core.actions.dispatch(
            name="fit.add",
            payload={"dataset_indices": [self.state["decay_dataset"]], "model_name": "Lifetime"},
        )
        window = self.wait_for(
            lambda: [w for w in gui.mdiarea.subWindowList() if isinstance(w, FitSubWindow)],
            30, "the fit window",
        )[-1]
        fit = window.fit
        ctrl = gui.findChildren(FittingControllerWidget)[-1]
        # The range boxes act on editingFinished: type into them as a user does.
        for box, text in ((ctrl.spinBox_2, "0"), (ctrl.spinBox, "255")):
            box.setFocus()
            QTest.keyClick(box, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
            QTest.keyClicks(box, text)
            QTest.keyClick(box, QtCore.Qt.Key_Return)
        self.pump(0.5)
        ctrl.button_fit.click()
        self.wait_for(lambda: float(getattr(fit, "chi2r", 0) or 0) > 0, 60, "the fit")
        self.state.update(fit=fit, fit_window=window)
        window.showMaximized()
        self.pump(1)
        png = self.grab("01_decay_fit")

        settings.cs_settings["optimization"]["sampling"].update(SAMPLING)
        target = self.scratch / "sampling"
        target.mkdir()
        chisurf.gui.widgets.get_directory = lambda *args, **kwargs: (str(target), None)
        ctrl.button_sample.click()
        member = getattr(fit, "selected_fit", fit)
        chain = self.wait_for(lambda: getattr(member, "sampling_chain", None), 300, "the chain")
        self.pump(3)  # the job's watcher polls every 1.5 s, then publishes fit.updated
        shape = tuple(chain["chains"].shape)
        assert shape[0] == SAMPLING["n_runs"] and shape[1] >= 8, shape
        assert list(target.glob("*/diagnostics.json")), "no diagnostics.json on disk"
        self.state.update(chain=chain["chains"].copy(), names=list(chain["parameter_names"]))
        return {"chi2r": float(fit.chi2r), "chain_shape": shape,
                "parameters": list(chain["parameter_names"]), "png": png}

    def diagnostics_page(self):
        """Clicking the Chain-diagnostics tab draws the chain, not a reason why it cannot."""
        self.need("fit_window", "chain")
        window = self.state["fit_window"]
        page = self._open_diagnostics_tab(window)
        assert page.state == "ok", f"page state {page.state!r}"
        names = [str(n).split(":")[-1] for n in self.state["names"]]
        assert list(page.parameters) == names, (page.parameters, names)
        self.state["page"] = page
        return {"state": page.state, "parameters": list(page.parameters),
                "png": self.grab("02_chain_diagnostics")}

    def autosave(self):
        """The project is written beside the working folder by the timer, with no dialog."""
        self.need("fit")
        from qtpy.QtWidgets import QApplication, QDialog

        gui = self.state["gui"]
        visible = {id(w) for w in QApplication.topLevelWidgets() if w.isVisible()}
        found = self.wait_for(
            lambda: sorted((self.scratch / "work").rglob("*.autosave.cs.pto")), 30, "the autosave file"
        )
        self.pump(1.5)  # one more tick, so the file holds the state after sampling
        assert QApplication.activeModalWidget() is None, "autosave raised a modal dialog"
        dialogs = [w for w in QApplication.topLevelWidgets()
                   if w.isVisible() and id(w) not in visible and isinstance(w, QDialog)]
        assert not dialogs, f"new dialogs: {dialogs}"
        from chisurf.core.project import storage
        from chisurf.core.project.lifecycle import snapshot_fingerprint

        loaded = storage.load_file(found[0])
        assert snapshot_fingerprint(loaded) == gui._autosave._last_fingerprint
        self.state["autosave"] = found[0]
        return {"file": str(found[0]), "bytes": found[0].stat().st_size}

    def reload(self):
        """Open the autosave copy: the same datasets, fit, parameters and chain come back."""
        self.need("autosave", "chain")
        import numpy as np

        from chisurf.core.project.lifecycle import SaveDecision
        from chisurf.gui import project_helpers

        cs, gui = self.state["cs"], self.state["gui"]
        member = getattr(self.state["fit"], "selected_fit", self.state["fit"])
        before = {
            "datasets": [d.name for d in cs.imported_datasets],
            "fits": [f.name for f in cs.fits],
            "parameters": {p.name: p.value for p in member.model.parameters_all},
        }
        asked = []
        # "Save changes before continuing?" -- the user answers Don't Save: the autosave is the copy.
        gui._save_decision = lambda: (asked.append(True), SaveDecision.DISCARD)[1]
        assert project_helpers.open_recent_project(gui, str(self.state["autosave"])) is not False
        self.pump(3)
        assert len(asked) == 1, f"one Open asked 'Save changes?' {len(asked)} times"
        fit = cs.fits[-1]
        member = getattr(fit, "selected_fit", fit)
        after = {
            "datasets": [d.name for d in cs.imported_datasets],
            "fits": [f.name for f in cs.fits],
            "parameters": {p.name: p.value for p in member.model.parameters_all},
        }
        assert after == before, {"before": before, "after": after}
        chain = getattr(member, "sampling_chain", None)
        assert chain is not None, "the chain did not survive the reload"
        assert np.allclose(chain["chains"], self.state["chain"]), "the chain changed on reload"
        from chisurf.gui.widgets.fitting import FitSubWindow

        windows = [w for w in gui.mdiarea.subWindowList() if isinstance(w, FitSubWindow)]
        assert windows, "no fit window after the reload"
        self.state.update(fit=fit, fit_window=windows[-1])
        return {"state": after["fits"], "save_prompts": len(asked)}

    def open_in_ndx(self):
        """The page's *Open in ndX* menu entry opens the stored chain as ndX's table."""
        self.need("fit_window", "chain")
        page = self._open_diagnostics_tab(self.state["fit_window"])
        assert page.state == "ok", f"page state after reload {page.state!r}"
        from qtpy.QtWidgets import QApplication

        shown = {id(w) for w in QApplication.topLevelWidgets() if w.isVisible()}
        dict(page.rank_plot._extra_menu_actions)["Open in ndX"]()
        from ndxplorer.app.frame import live_apps

        app = self.wait_for(lambda: live_apps(), 30, "an ndX window")[-1]

        def loaded():
            app.request_frame() if callable(getattr(app, "request_frame", None)) else None
            return getattr(app.model, "has_data", False)

        self.wait_for(loaded, 60, "ndX to load the chain")
        source = app.model.source
        n_chains, n_draws = self.state["chain"].shape[:2]
        assert source.size == n_chains * n_draws, (source.size, n_chains, n_draws)
        columns = [source.store.column(i).name() for i in range(source.store.n_columns())]
        names = [str(n).split(":")[-1] for n in self.state["names"]]
        assert all(any(n in c for c in columns) for n in names), (names, columns)
        self.pump(2)
        hosts = [w for w in QApplication.topLevelWidgets() if w.isVisible() and id(w) not in shown]
        assert hosts, "ndX opened no window"
        host = max(hosts, key=lambda w: w.width() * w.height())
        return {"path": str(app.model.path), "rows": source.size, "columns": columns,
                "window": host.windowTitle(), "png": self.grab("03_ndx_chain", host)}

    def legacy_export(self):
        """The container unpacks to a folder the legacy readers open: ``.bur`` plus ``.bg4``."""
        self.need("run")
        from chisurf.core.fio.fluorescence.burst import read_bur_file
        from chisurf.core.fio.fluorescence.burst_companion import read_companion
        from chisurf.plugins.core.pto_inspector.core import export_legacy

        demo = self.state["demo"]
        out = self.scratch / "legacy"
        written = export_legacy(self.state["pto"], out)
        bur = out / self.state["run"] / "bi4_bur" / "bs_demo.bur"
        bg4 = out / self.state["run"] / "bg4" / "bs_demo.bg4"
        assert bur in written and bg4 in written, written
        table = read_bur_file(bur)
        from chisurf.core.datastore import row_count

        assert row_count(table) == 2 * demo.N_BURSTS + 1, row_count(table)  # zero-interleaved
        columns, rows = read_companion(bg4)
        assert rows.shape[0] == demo.N_BURSTS, rows.shape
        return {"written": [str(p.relative_to(out)) for p in written], "bg4_columns": columns[:6]}

    # -- helpers --------------------------------------------------------------------------------------- #
    def _tables(self, *, operation: str = "", name: str = "") -> dict:
        """``{artifact name: rows}`` of the container's tables of one operation (or one name)."""
        from chisurf.core.fio.pto import Measurement

        out = {}
        with Measurement.open(self.state["pto"]) as m:
            for obj in m.artifacts():
                op = str(m.tag(obj.uid, "_mmfdb_operation.operation_type"))
                if (operation and op == operation) or (name and str(obj.name) == name):
                    out[str(obj.name)] = int(getattr(obj, "rows", 0) or 0)
        return out

    def _open_diagnostics_tab(self, window):
        """Click the fit window's Chain-diagnostics tab; return its page once drawn."""
        tabs = window.plot_tab_widget
        titles = [tabs.tabText(i) for i in range(tabs.count())]
        index = titles.index("Chain diagnostics")
        tabs.setCurrentIndex(index)
        page = self.wait_for(lambda: window._plots_all[index], 10, "the diagnostics page")
        self.pump(1)
        return page


def worker(scratch: Path) -> None:
    """Run the scenario in this process (a fresh one: settings are read once, at import)."""
    for name in ("settings", "mmfdb", "home", "tmp", "cache"):
        (scratch / name).mkdir(parents=True, exist_ok=True)
    os.environ.update(
        CHISURF_SETTINGS_DIR=str(scratch / "settings"),
        MMFDB_SETTINGS_DIR=str(scratch / "mmfdb"),
        MMFDB_DATABASE_PATH=str(scratch / "mmfdb.sqlite"),
        MMFDB_OBJECT_STORE_ROOT=str(scratch / "objects"),
        XDG_CACHE_HOME=str(scratch / "cache"),
        HOME=str(scratch / "home"),
        TMPDIR=str(scratch / "tmp"),
        QT_QPA_PLATFORM="offscreen",
        MPLBACKEND="Agg",
    )
    import tempfile

    tempfile.tempdir = None  # re-read TMPDIR
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    scenario = Scenario(scratch)
    scenario.run()


# ---------------------------------------------------------------------------------------------- the tests
@pytest.fixture(scope="module")
def scenario(tmp_path_factory) -> dict:
    """Run the worker once; return its per-step record."""
    OUT.mkdir(parents=True, exist_ok=True)
    RESULT.unlink(missing_ok=True)
    scratch = tmp_path_factory.mktemp("release-scenario")
    env = dict(os.environ)
    sources = [str(REPO), str(REPO / "modules" / "chinet"), str(REPO / "modules" / "imp-tricks" / "src"),
               str(REPO / "modules" / "mmfdb" / "src")]
    if env.get("PYTHONPATH"):
        sources.append(env["PYTHONPATH"])
    env.update(PYTHONPATH=os.pathsep.join(sources), PYTHONUNBUFFERED="1", QT_QPA_PLATFORM="offscreen")
    # Under the e2e task's per-test --timeout=300; the walk takes about 30 s.
    timeout = float(os.environ.get("CHISURF_RELEASE_SCENARIO_TIMEOUT", "240"))
    log = OUT / "worker.log"
    with open(log, "w", encoding="utf-8") as handle:
        try:
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", str(scratch)],
                           cwd=REPO, env=env, stdout=handle, stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired:
            pass  # the record says how far it got
    if not RESULT.exists():
        pytest.fail(f"the scenario worker wrote no result; see {log}")
    return json.loads(RESULT.read_text(encoding="utf-8"))


def _param(step: str):
    """The step as a test parameter, strict-xfail when its product half is missing."""
    marks = [pytest.mark.xfail(strict=True, reason=XFAIL[step])] if step in XFAIL else []
    return pytest.param(step, marks=marks, id=step)


@pytest.mark.e2e
@pytest.mark.parametrize("step", [_param(s) for s in STEPS])
def test_release_scenario(scenario, step):
    """Each step of the walk passed in the real app."""
    record = scenario.get(step)
    assert record is not None, f"the worker never reached {step!r} (timed out or crashed; see worker.log)"
    detail = record.get("traceback") or record.get("error") or record.get("observed")
    assert record["status"] == "passed", f"{step}: {record['status']}\n{detail}"


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        try:
            worker(Path(sys.argv[2]))
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            # Qt, the RPC server thread and the sampler pools need no orderly teardown here.
            os._exit(0)
