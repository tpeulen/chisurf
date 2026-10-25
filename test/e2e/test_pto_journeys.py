"""The .pto-only user journeys, clicked through the real UI (PRD-154 item 13).

One walk, one method per leg, in the order a user meets them: the shell starts,
the Burst Selection tool opens *through* the shell, a ``.pto`` container is added
with the tool's own Add-files affordance (the file dialog is fed, never
bypassed), the search runs, the histograms and the GMM populations appear, the
sub-ensemble decay is written *and fitted in the shell's Analysis dock*, the
same container feeds the burstwise FCS tool, ndX opens the stored tables, the
identical search runs on the RAW vendor folder (filesystem parity: the old
workflow must survive beside the container), and the project round-trips.

A leg fails when its affordance is missing -- the point of this walk is the UX,
so every step first asserts the button/dock that leads to the next stage exists,
then exercises it. The walk never stops early: each step records its outcome in
``test/e2e/pto_journeys/result.json`` (and a PNG), so a dead end names itself.
"""

from __future__ import annotations

import json
import socket
import time
import traceback
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
OUT = HERE / "pto_journeys"
RESULT = OUT / "result.json"

STEPS = [
    "start_shell",
    "open_burst_tool",
    "container_open",
    "burst_search",
    "gmm_populations",
    "decay_from_bursts",
    "fit_the_decay",
    "burstwise_fcs",
    "ndx_stores",
    "filesystem_parity",
    "project_roundtrip",
]


class Blocked(OSError, RuntimeError):
    """A leg could not run because an earlier leg left nothing to build on."""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Journeys:
    """The walk, one method per leg; ``state`` carries what later legs need."""

    def __init__(self, scratch: Path) -> None:
        self.scratch = scratch
        self.state: dict = {}
        self.results: dict = {}
        self.driver = None
        self.shell = None
        self._dialog_feed: list = []
        self._drivers: dict = {}

    # -- plumbing --------------------------------------------------------------------------------- #
    def pump(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.driver is not None:
                self.driver.frame(1)
            time.sleep(0.02)

    def wait_for(self, predicate, timeout: float, what: str):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = predicate()
            if value:
                return value
            self.pump(0.1)
        raise AssertionError(f"timed out after {timeout:g}s waiting for {what}")

    def need(self, *keys: str) -> None:
        missing = [k for k in keys if k not in self.state]
        if missing:
            raise Blocked(f"blocked: needs {', '.join(missing)} from an earlier leg")

    def grab(self, name: str) -> str:
        path = OUT / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        if self.driver is not None:
            self.driver.screenshot(path)
            return str(path)
        raise AssertionError("no driver available to save screenshot")

    def write(self) -> None:
        RESULT.write_text(json.dumps(self.results, indent=2, default=str), encoding="utf-8")

    def drive(self, app):
        """The shell has its driver; every other app gets one cached Driver."""
        from emtk.testing import Driver

        if app is self.shell:
            return self.driver
        if id(app) not in self._drivers:
            self._drivers[id(app)] = Driver(app, size=(1400, 900))
            self._drivers[id(app)].frame(2)
        return self._drivers[id(app)]

    def click(self, app, key: str):
        """Assert the affordance *key* is drawn, then click it."""
        rects = getattr(app, "item_rects", None) or {}
        assert key in rects, (
            f"dead end: '{key}' is not drawn by {type(app).__name__} "
            f"(drawn: {sorted(rects)[:24]})"
        )
        assert rects[key][2] > 0 and rects[key][3] > 0, f"'{key}' has no area"
        self.drive(app).click(key)
        if app is self.shell:
            self.pump(0.1)
        return True

    def run(self) -> None:
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
            except BaseException as exc:  # noqa: BLE001 - every outcome recorded, none end the walk
                record.update(
                    status="failed",
                    error=f"{type(exc).__name__}: {exc}",
                    traceback=traceback.format_exc(),
                )
                try:
                    self.grab(f"{step}_failed")
                except BaseException:
                    pass
            record["seconds"] = round(time.monotonic() - start, 2)
            self.write()

    # -- the legs --------------------------------------------------------------------------------- #
    def start_shell(self):
        """The main window comes up with its data and analysis docks."""
        from mmfdb.security import credentials

        credentials.store_session_token = lambda *a, **k: False
        credentials.load_session_token = lambda *a, **k: None

        from emtk.file_dialog import FileDialog
        from emtk.testing import Driver

        import chisurf
        from chisurf.core import settings
        from chisurf.emtk.main_app import EmtkShellApp
        from chisurf.emtk.session import start_session

        settings.cs_settings.setdefault("mmfdb", {}).update(
            cmd_port=_free_port(), pub_port=_free_port()
        )

        session = start_session()
        app = EmtkShellApp(session_factory=lambda **kw: session)
        app.data.adopt(session)
        driver = Driver(app, size=(1440, 900))
        driver.frame(3)

        from types import SimpleNamespace

        chisurf.cs = app
        app.modelLayout = None
        app.plotOptionsLayout = None
        app.mdiarea = SimpleNamespace(setUpdatesEnabled=lambda *a: None)
        app._open_fit_subwindow = lambda *a: None
        app._get_project_document = lambda: app.project.document
        chisurf.working_path = str(self.scratch / "work")
        (self.scratch / "work").mkdir(exist_ok=True)

        # The file dialogs of every tool in the walk are FED, never bypassed:
        # a leg queues what its chooser should return, the patch hands it over.
        journeys = self

        def feed_file_dialog(dialog, *args, **kwargs):
            journeys.state["dialogs_opened"] = journeys.state.get("dialogs_opened", 0) + 1
            if journeys._dialog_feed:
                return [journeys._dialog_feed.pop(0)]
            return False

        FileDialog.draw = feed_file_dialog

        self.shell = app
        self.driver = driver
        self.state.update(app=app, driver=driver, session=session, cs=chisurf)
        assert not app.project.dialogs.modal, "a modal dialog stayed open after start"
        return {"plugins": len(app.by_id)}

    def open_burst_tool(self):
        """The Burst Selection tool opens through the shell (a user's entry)."""
        self.need("app")
        hosted = self.shell.open_plugin("burst_analysis")
        assert hosted is not None, "dead end: the shell cannot open the Burst Selection tool"
        self.wait_for(lambda: hosted.app is not None, timeout=60, what="the tool to build")
        assert not hosted.error, f"the tool failed to build: {hosted.error}"
        tool = hosted.app
        self.wait_for(
            lambda: bool(getattr(tool, "item_rects", {})),
            timeout=60,
            what="the hub's navigation",
        )
        assert "nav.selection" in tool.item_rects, (
            "dead end: the hub does not offer the Burst Selection step "
            f"(drawn: {sorted(tool.item_rects)[:20]})"
        )
        self.drive(tool).click("nav.selection")
        self.wait_for(
            lambda: "selection" in getattr(tool, "children", {}),
            timeout=30,
            what="the selection step to open",
        )
        selection = tool.children["selection"]
        self.wait_for(
            lambda: bool(getattr(selection, "item_rects", {})),
            timeout=30,
            what="the selection step's affordances",
        )
        assert "add_files" in selection.item_rects, "the Add-files affordance is missing"
        self.state.update(burst_tool=selection, burst_hosted=hosted, hub=tool)
        return {"hub_children": sorted(tool.children),
                "affordances": sorted(selection.item_rects)[:12]}

    def container_open(self):
        """W1 leg 1: Add files -> the demo .pto -> the run appears; no sibling folder needed."""
        self.need("burst_tool")
        from chisurf.core.fio.pto import Measurement

        from chisurf.plugins.burst.burst_selection import demo

        spc = demo.make_demo(self.scratch / "data")
        with Measurement.create(spc, title="Journey demo") as m:
            pto = Path(m.path)
        spc.unlink()  # from here on the container is the only copy of the photons
        spc.with_suffix(".json").unlink(missing_ok=True)

        self._dialog_feed = [str(pto)]
        self.click(self.state["burst_tool"], "add_files")
        tool = self.state["burst_tool"]
        self.wait_for(
            lambda: len(tool.model.files) > 0, timeout=20, what="the container in the files list"
        )
        first = tool.model.files[0]
        assert (Path(first) if not isinstance(first, Path) else first) == pto, first
        self.state.update(pto=pto, demo=demo, tool_model=tool.model)
        return {"container": str(pto), "files": 1}

    def burst_search(self):
        """W1 leg 2: Run finds every planted burst; the histogram docks draw."""
        self.need("tool_model", "demo")
        tool, m, demo = self.state["burst_tool"], self.state["tool_model"], self.state["demo"]
        m.set_setup({**demo.SETUP, "setup_name": ""})
        assert m.prepare_run() is None, m.blocked_reason()
        self.click(tool, "toolAction_run")
        row = self.wait_for(
            lambda: next((r for r in m.run_rows() if r.get("rows") == demo.N_BURSTS), None),
            timeout=300,
            what=f"the search to find all {demo.N_BURSTS} planted bursts",
        )
        m.select_run(row)
        # the Summary dock reads the same metadata; the result must PUBLISH (a drawn frame)
        self.wait_for(
            lambda: (m.result or {}).get("metadata", {}).get("n_bursts") == demo.N_BURSTS,
            timeout=120,
            what="the search result to publish (n_bursts in the summary)",
        )
        assert m.n_bursts == demo.N_BURSTS, f"{m.n_bursts} bursts, {demo.N_BURSTS} planted"
        for dock in ("histogram", "trace"):
            assert dock in tool.item_rects, f"dead end: the {dock} panel affordance is missing"
        assert not list(self.state["pto"].parent.glob("*#*")), (
            "a .pto input must not get a legacy folder beside it"
        )
        self.state.update(run=row["run_name"])
        self.grab("w1_burst_search")
        return {"bursts": m.n_bursts, "run": row["run_name"]}

    def gmm_populations(self):
        """W1 leg 3: fit GMM on the burst histogram -> populations appear."""
        self.need("burst_tool", "tool_model")
        tool, m = self.state["burst_tool"], self.state["tool_model"]
        if not getattr(m, "run_name", "") and m.run_rows():
            m.select_run(m.run_rows()[0])
        self.wait_for(
            lambda: m.histogram() is not None,
            timeout=120,
            what="the feature histogram of the selected run",
        )
        # the GMM settings panel's fields (the demo plants two FRET species)
        assert "gmm_settings" in tool.item_rects, "dead end: no GMM settings affordance"
        m.gmm_components = 2
        m.gmm_result = None  # earlier frames may have left a skip verdict
        self.click(tool, "fit_gmm")
        self.wait_for(
            lambda: m.gmm_result is not None,
            timeout=180,
            what="the GMM verdict",
        )
        result = m.gmm_result or {}
        assert "error" not in result, result.get("error")
        populations = result.get("components") or []
        assert populations, f"the GMM fit produced no populations ({m.status_text})"
        self.grab("w1_gmm")
        return {"populations": len(populations), "n": result.get("n"), "status": m.status_text[:120]}

    def decay_from_bursts(self):
        """W2 leg 1: Decay from selected bursts -> decay beside the run AND a dataset."""
        self.need("tool_model", "cs")
        m, cs = self.state["tool_model"], self.state["cs"]
        m.decay_bins = 256
        before = len(cs.imported_datasets)
        verdict = m.write_decay()
        assert verdict.startswith(f"Decay of {self.state['demo'].N_BURSTS} bursts"), verdict
        assert "registered as a dataset" in verdict, verdict
        assert len(cs.imported_datasets) == before + 1
        dataset = cs.imported_datasets[-1]
        self.state.update(decay_dataset=dataset, decay_name=dataset.name)
        self.grab("w2_decay_written")
        return {"verdict": verdict[:120], "dataset": dataset.name}

    def fit_the_decay(self):
        """W2 leg 2: the shell's Datasets dock lists the decay; a fit runs on it."""
        self.need("app", "decay_dataset")
        app, dataset = self.shell, self.state["decay_dataset"]
        docks, panel = app.data, app.data.datasets
        rows = panel.dataset_rows()
        names = [r.get("name") for r in rows] if rows else []
        assert names, "dead end: the Datasets dock lists no datasets"
        assert any(self.state["decay_name"] in str(n) for n in names), (
            f"dead end: the sub-ensemble decay {self.state['decay_name']!r} "
            f"is not visible in the Datasets dock (rows: {names[:6]})"
        )
        record = next(r for r in rows if self.state["decay_name"] in str(r.get("name")))
        panel.select_dataset(record)
        model_names = panel.model_names()
        assert model_names, "dead end: no fit model offered for a decay dataset"
        decay_models = [
            n
            for n in model_names
            if any(w in n.lower() for w in ("lifetime", "decay", "expo"))
        ]
        assert decay_models, f"dead end: no decay model among {model_names[:8]}"
        panel.model = decay_models[0]
        assert panel.selected_rows(), "dead end: the decay row is not selectable"
        panel.add_fit()  # the + Analysis button's handler
        self.wait_for(lambda: docks.current_uid and not docks.busy, timeout=60, what="the new fit")
        fits = panel.fit_rows()
        assert fits, "dead end: creating the fit added no fit row"
        # the Run affordance of the Analysis dock, then the chi-square it reports
        assert docks.run_fit(), "dead end: the Analysis dock's Run refused"
        self.wait_for(lambda: not docks.busy, timeout=180, what="the fit to finish")
        self.pump(1.0)
        chi2r = docks.analysis.info.get("chi2r_current", docks.analysis.info.get("chi2r"))
        assert chi2r is not None and 0.0 < float(chi2r) < 100.0, (
            f"the fit window reports no sane chi-square ({docks.analysis.info})"
        )
        self.grab("w2_fit")
        return {
            "dataset_rows": len(rows),
            "model": decay_models[0],
            "n_fits": len(fits),
            "chi2r": round(float(chi2r), 4),
        }

    def burstwise_fcs(self):
        """W3: the same container feeds the burstwise FCS tool; curves land in it."""
        self.need("app", "pto", "run")
        hosted = self.shell.open_plugin("burst_fcs_correlator")
        assert hosted is not None, "dead end: the shell cannot open the FCS correlator"
        self.wait_for(lambda: hosted.app is not None, timeout=60, what="the FCS tool to build")
        assert not hosted.error, f"the FCS tool failed to build: {hosted.error}"
        fcs = hosted.app
        self.wait_for(
            lambda: bool(getattr(fcs, "item_rects", {})), timeout=60, what="the FCS affordances"
        )
        ctrl = getattr(fcs, "controller", None) or getattr(fcs, "model", None)
        assert ctrl is not None, "the FCS window exposes no controller"
        import json as _json

        ctrl.apply_pairs(_json.dumps([{"pair_name": "ACF_green", "chs_a": [0], "chs_b": [0]}]))
        self._dialog_feed = [str(self.state["pto"])]
        key = next((k for k in ("add_files", "open") if k in fcs.item_rects), None)
        assert key, f"dead end: no add-files affordance in the FCS window ({sorted(fcs.item_rects)[:12]})"
        self.click(fcs, key)
        self.wait_for(lambda: len(getattr(ctrl, "files", []) or []) > 0, timeout=60, what="the container in the FCS input list")
        rows = self.wait_for(lambda: ctrl.run_rows() or None, timeout=120, what="the FCS run picker")
        ctrl.select_run(ctrl.run_rows()[-1])
        ctrl._on_run()
        end = time.monotonic() + 180
        while getattr(ctrl, "_future", None) is not None and time.monotonic() < end:
            self.pump(0.1)
            ctrl.poll()
        assert getattr(ctrl, "_future", None) is None, "burstwise FCS did not finish"
        demo = self.state["demo"]
        assert len(ctrl._curves) == demo.N_BURSTS, ctrl.status
        try:
            ctrl.close()
        except Exception:
            pass
        from chisurf.core.fio.pto import Measurement

        with Measurement.open(self.state["pto"]) as mm:
            tables = [str(o.name) for o in mm.artifacts() if "fcs" in str(o.kind).lower()]
        assert tables, "no burst-fcs table in the container"
        self.grab("w3_fcs")
        return {"curves": len(ctrl._curves), "tables": tables[:4]}

    def ndx_stores(self):
        """W4: the stored tables open in ndX (affordance: the tool's Open-in-ndX)."""
        self.need("burst_tool", "pto")
        tool = self.state["burst_tool"]
        assert "ndx_current" in tool.item_rects, (
            "dead end: the Open-in-ndX affordance is missing after a search"
        )
        opened = tool.send_to_ndx()
        assert opened, f"Open in ndX refused: {tool.model.status_text}"
        self.pump(0.5)
        self.grab("w4_ndx")
        return {"status": tool.model.status_text[:120]}

    def filesystem_parity(self):
        """W5: the SAME search runs on the raw vendor folder, container never involved."""
        self.need("demo", "burst_tool")
        demo, tool = self.state["demo"], self.state["burst_tool"]
        raw = demo.make_demo(self.scratch / "raw")  # the legacy .spc folder, no .pto anywhere
        assert not list(self.scratch.joinpath("raw").glob("*.pto"))
        m2 = tool.model.__class__()
        m2.set_setup({**demo.SETUP, "setup_name": ""})
        assert m2.add_paths([raw]) == 1
        assert m2.prepare_run() is None, m2.blocked_reason()
        m2.run()
        assert m2.n_bursts == demo.N_BURSTS, f"raw-folder search found {m2.n_bursts}"
        self.state.update(raw_model=m2)
        return {"raw": str(raw), "bursts": m2.n_bursts, "legacy_folder_needed": False}

    def project_roundtrip(self):
        """W6: the project (with the fit) saves and reopens; the datasets survive."""
        self.need("app", "cs")
        app, cs = self.shell, self.state["cs"]
        project_path = self.scratch / "work" / "journey.cs.pto"
        self._dialog_feed = [str(project_path)]
        assert app.project.save(save_as=True), "dead end: Save Project refused"
        self.wait_for(lambda: project_path.exists(), timeout=30, what="the project file")
        before = len(cs.imported_datasets)
        n_fits_before = len(app.data.datasets.fit_rows())
        self._dialog_feed = [str(project_path)]
        assert app.project.open_project(), "dead end: Open Project refused"
        self.pump(2.0)
        after = len(cs.imported_datasets)
        assert after >= before, "the reopened project lost datasets"
        self.grab("w6_reopened")
        return {
            "project": str(project_path),
            "datasets_before": before,
            "datasets_after": after,
            "fits_before": n_fits_before, "fits_after": len(app.data.datasets.fit_rows()),
        }


@pytest.mark.slow
def test_pto_only_user_journeys(tmp_path_factory):
    """Run the whole journey walk; the assertion is that every leg passed."""
    scratch = tmp_path_factory.mktemp("pto_journeys")
    OUT.mkdir(parents=True, exist_ok=True)
    journeys = Journeys(scratch)
    try:
        journeys.run()
    finally:
        journeys.write()
        if journeys.shell is not None:
            try:
                journeys.shell.close()
            except Exception:
                pass
    failed = {k: v for k, v in journeys.results.items() if v["status"] != "passed"}
    assert not failed, json.dumps(failed, indent=2, default=str)
    assert len(journeys.results) == len(STEPS)
