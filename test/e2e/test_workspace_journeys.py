"""Workspace journeys: every file-based workflow from ONE drop, in the real UI.

The acceptance of the data workspace (``okf/specs/data-workspace.md``, "Acceptance"): the
user does not open files. Data enters through the shell's drop -- the one input entry point --
lands in the Datasets workspace of a ``.cs.pto`` project, and every tool takes its input from
there (``EmtkShellApp.feed_from_workspace``: what *Open in…* and a drag onto a tool call).
Results go back into the project, so the next step picks them from the workspace too.

Each leg runs in a process of its own (the click-all pattern): a native abort costs one leg,
not the walk. A guard sits on every input route a plugin could take instead -- an emtk
``FileDialog`` drawn in ``open``/``folder`` mode, ``card_shell`` file choosers, the MMFDB
``DatasetPicker`` -- and records the call site; any record fails the leg. Save dialogs (writing
an output) are allowed and fed. Each leg writes ``workspace_journeys/<leg>.json`` and PNGs.

A leg whose tool has not been migrated yet -- its manifest declares no ``from_workspace`` input,
or it is still on ``test/input_file_dialog_allowlist.txt`` -- is ``xfail(strict=True)`` with
the tool named, computed at collection: the marks disappear as the migration lands, and from
then on the leg must pass. Heavy: run on the remote box (``build_tools/remote_test.sh``);
locally one leg at a time with ``-k``.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "workspace_journeys"
ALLOWLIST = REPO / "test" / "input_file_dialog_allowlist.txt"

#: The input routes the guard watches, and the one place allowed to ask for an input file:
#: the shell's own Read data / Add data entry (the single entry point).
ENTRY_POINT_FILES = ("chisurf/emtk/fit_docks.py",)
INPUT_MODES = ("open", "folder")


@dataclass
class Leg:
    """One journey: what is dropped, which tools it feeds, what it proves."""

    doc: str
    tools: tuple[str, ...] = ()
    needs_kinds: tuple[str, ...] = ()
    known_open: str = ""  # a decision or feature still open; xfail with this reason
    depends: tuple[str, ...] = field(default_factory=tuple)


LEGS: dict[str, Leg] = {
    "drop_photons": Leg("Raw vendor photon files dropped on the shell become linked photons rows."),
    "drop_container": Leg(
        "A dropped .pto adds its photon streams and burst runs as rows.", needs_kinds=("bursts",)
    ),
    "burst_chain": Leg(
        "photons -> burst search -> runs appear as children -> GMM -> sub-ensemble decay "
        "(registered) -> fit in the Analysis dock",
        tools=("burst_selection",),
    ),
    "fcs_from_photons": Leg(
        "photons -> FCS correlation -> correlation row -> fit", tools=("fcs_correlator",)
    ),
    "trace_and_windows": Leg(
        "photons -> intensity trace; photons + setup -> time windows",
        tools=("intensity_trace", "tttr_time_windows"),
    ),
    "burst_run_consumers": Leg(
        "a burst run row -> burstwise FCS, MLE, BVA, ndX",
        tools=("burst_fcs_correlator", "burst_mle_analysis", "burst_bva", "ndxplorer"),
        needs_kinds=("bursts",),
    ),
    "decay_tools": Leg(
        "a decay curve row -> LLTF, MaxEnt, IRF estimator",
        tools=("lltf", "maxent_decay", "irf_estimator"),
    ),
    "photon_image": Leg(
        "a CLSM photon stream (an image of photon events) -> pixel intensity map",
        tools=("img_pixel_intensity",),
        needs_kinds=("image",),
    ),
    "intensity_image": Leg(
        "an intensity stack -> PSF determination, FRC",
        tools=("psf_determination", "img_frc"),
        needs_kinds=("image",),
    ),
    "structure": Leg(
        "a structure -> ChiMOL, FRET docking (accessible volumes)",
        tools=("chimol", "fret_docking"),
        needs_kinds=("structure",),
    ),
    "setup_json": Leg(
        "a detector setup JSON dropped -> a setup row the micro-time histogram uses with photons",
        tools=("microtime_histogram",),
        needs_kinds=("setup",),
    ),
    "project_link_embed": Leg(
        "photons linked -> project saved and reopened (link resolves) -> Embed in project -> "
        "saved self-contained"
    ),
    "locate_missing": Leg(
        "a linked target moved -> Locate missing data finds it by name + sha256 -> relinked",
        known_open=(
            "Locate missing data asks for a search folder through a folder dialog -- an input "
            "dialog outside the single entry point (owner decision: allowed for repair, or the "
            "search runs over the workspace / project folders only)"
        ),
    ),
    "zenodo_gate": Leg("a project that only links its data is refused by the Zenodo export gate"),
}


# -- collection-time marks ----------------------------------------------------------------- #
def _allowlisted() -> set[str]:
    if not ALLOWLIST.is_file():
        return set()
    out = set()
    for line in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line.split()[0].split("/")[-1].split(":")[0])
    return out


def _manifests() -> dict[str, dict]:
    out = {}
    for path in (REPO / "chisurf" / "plugins").rglob("manifest.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("id"):
            out[str(data["id"])] = {**data, "_dir": path.parent.name}
    return out


def _declares_workspace_input(manifest: dict) -> bool:
    return any(
        isinstance(a, dict) and a.get("from_workspace") for a in manifest.get("accepts") or []
    )


def _known_kinds() -> set[str]:
    try:
        from chisurf.core.data_kinds import KINDS
    except Exception:  # noqa: BLE001 - no kinds module: nothing is known
        return set()
    return set(KINDS)


def _not_ready(leg: Leg) -> str:
    """Why *leg* cannot pass yet (``""``: it must pass)."""
    if leg.known_open:
        return leg.known_open
    missing = [k for k in leg.needs_kinds if k not in _known_kinds()]
    if missing:
        return f"data kind not built yet: {', '.join(missing)}"
    manifests, allow = _manifests(), _allowlisted()
    pending = []
    for tool in leg.tools:
        m = manifests.get(tool)
        if m is None:
            pending.append(f"{tool} (no manifest)")
        elif not _declares_workspace_input(m) or tool in allow or m.get("_dir") in allow:
            pending.append(tool)
    return f"not migrated yet: {', '.join(pending)}" if pending else ""


def _params():
    for name, leg in LEGS.items():
        reason = _not_ready(leg)
        marks = [pytest.mark.xfail(strict=True, reason=reason)] if reason else []
        yield pytest.param(name, id=name, marks=marks)


# -- the walk, in a child process ---------------------------------------------------------- #
class InputRouteUsed(AssertionError):
    """A tool asked the user for an input file instead of taking it from the workspace."""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _call_site() -> str:
    """The first frame outside emtk/the guard that asked: the plugin line to migrate."""
    for frame in reversed(traceback.extract_stack()[:-2]):
        name = frame.filename.replace(os.sep, "/")
        if "/chisurf/" in name and "test_workspace_journeys" not in name:
            return f"{name.split('/chisurf/', 1)[-1]}:{frame.lineno} ({frame.name})"
    return "unknown"


class Walk:
    """One shell, one project, one leg; ``violations`` collects every input route taken."""

    def __init__(self, scratch: Path, leg: str) -> None:
        self.scratch = scratch
        self.leg = leg
        self.out = OUT / leg
        self.violations: list[str] = []
        self.save_feed: list[str] = []
        self.shell = None
        self.driver = None
        self.observed: dict = {}

    # plumbing ------------------------------------------------------------------------------- #
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

    def grab(self, name: str) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        if self.driver is not None:
            self.driver.screenshot(self.out / f"{name}.png")

    def violation(self, what: str) -> None:
        site = _call_site()
        if any(site.startswith(entry) for entry in ENTRY_POINT_FILES):
            return  # the shell's one Add-data entry point
        self.violations.append(f"{what} at {site}")

    # the guard -------------------------------------------------------------------------------- #
    def install_guard(self) -> None:
        from emtk import file_dialog

        walk = self
        drawn: set[int] = set()

        def draw(dialog, *args, **kwargs):
            if dialog.mode == "save":
                return [walk.save_feed.pop(0)] if walk.save_feed else False
            if id(dialog) not in drawn:
                drawn.add(id(dialog))
                walk.violation(f"input FileDialog(mode={dialog.mode!r}, title={dialog.title!r})")
            return False  # an input dialog never hands a file over in this walk

        file_dialog.FileDialog.draw = draw

        try:
            from chisurf.emtk import card_shell
        except Exception:  # noqa: BLE001 - no card shell: nothing to watch there
            card_shell = None
        if card_shell is not None:
            for owner in vars(card_shell).values():
                if not isinstance(owner, type):
                    continue
                for name in ("choose_file", "open_file"):
                    original = owner.__dict__.get(name)
                    if callable(original):

                        def guarded(self_, *a, _name=name, **k):
                            walk.violation(f"card_shell.{_name}")
                            return None

                        setattr(owner, name, guarded)

        try:
            from chisurf.emtk import dataset_picker
        except Exception:  # noqa: BLE001
            dataset_picker = None
        if dataset_picker is not None:
            original_open = getattr(dataset_picker.DatasetPicker, "open", None)

            def picker_open(self_, *a, **k):
                walk.violation("MMFDB DatasetPicker -> local path")
                return original_open(self_, *a, **k) if callable(original_open) else None

            dataset_picker.DatasetPicker.open = picker_open

    # the shell and the one entry point ----------------------------------------------------- #
    def start_shell(self) -> None:
        from mmfdb.security import credentials

        credentials.store_session_token = lambda *a, **k: False
        credentials.load_session_token = lambda *a, **k: None

        from emtk.testing import Driver

        import chisurf
        from chisurf.core import settings
        from chisurf.emtk.main_app import EmtkShellApp
        from chisurf.emtk.session import start_session

        settings.cs_settings.setdefault("mmfdb", {}).update(
            cmd_port=_free_port(), pub_port=_free_port()
        )
        self.install_guard()
        session = start_session()
        app = EmtkShellApp(session_factory=lambda **kw: session)
        app.data.adopt(session)
        self.driver = Driver(app, size=(1440, 900))
        self.driver.frame(3)
        chisurf.cs = app
        chisurf.working_path = str(self.scratch / "work")
        (self.scratch / "work").mkdir(exist_ok=True)
        self.shell = app

    def rows(self, kind: str | None = None) -> list[dict]:
        rows = list(self.shell.data.datasets.dataset_rows() or [])
        return [r for r in rows if kind is None or r.get("kind") == kind]

    def drop(self, paths, kind: str, *, n: int = 1, timeout: float = 120) -> list[dict]:
        """The one entry point: drop *paths* on the shell; wait for *n* rows of *kind*."""
        before = {str(r.get("uid")) for r in self.rows(kind)}
        handled = self.shell.data.drop([str(p) for p in paths])
        assert handled, f"the drop of {[Path(p).name for p in paths]} was not taken"
        rows = self.wait_for(
            lambda: (
                [r for r in self.rows(kind) if str(r.get("uid")) not in before][:n]
                if len([r for r in self.rows(kind) if str(r.get("uid")) not in before]) >= n
                else None
            ),
            timeout,
            f"{n} new {kind} row(s) in the workspace",
        )
        self.show_workspace()
        return rows

    def show_workspace(self) -> None:
        """Bring the Datasets dock to the front, so the leg's pictures show the workspace."""
        docks = getattr(self.shell, "docks", None)
        for key in ("data.sets", "datasets"):
            try:
                docks.focus(key)
                break
            except Exception:  # noqa: BLE001 - a layout without that dock key
                continue
        self.pump(0.3)

    def feed(self, plugin_id: str, rows: list[dict], *, timeout: float = 120):
        """What *Open in…* / a drag onto the tool does: the tool takes the rows' addresses."""
        hosted = self.shell.feed_from_workspace(plugin_id, rows)
        assert hosted is not None, (
            f"dead end: {plugin_id} does not take {[r.get('kind') for r in rows]} from the "
            f"workspace ({self.shell.status})"
        )
        self.wait_for(lambda: hosted.app is not None, timeout, f"{plugin_id} to build")
        assert not hosted.error, f"{plugin_id} failed to build: {hosted.error}"
        app = hosted.app
        names = {Path(str(r.get("address") or "")).name for r in rows if r.get("address")}
        if names:
            self.wait_for(
                lambda: _holds(app, names), timeout, f"{plugin_id} to hold {sorted(names)}"
            )
        self.pump(0.3)
        return app

    def check(self) -> None:
        if self.violations:
            raise InputRouteUsed("input routes taken:\n  " + "\n  ".join(self.violations))


def _holds(app, names: set[str], depth: int = 3) -> bool:
    """Whether *app* (its model/controller, a few levels down) holds a reference to *names*."""
    seen: set[int] = set()

    def walk(obj, level: int) -> bool:
        if id(obj) in seen or level < 0:
            return False
        seen.add(id(obj))
        if isinstance(obj, (str, Path)):
            text = str(obj)
            return any(n and n in text for n in names)
        if isinstance(obj, dict):
            return any(walk(v, level - 1) for v in list(obj.values())[:200])
        if isinstance(obj, (list, tuple, set)):
            return any(walk(v, level - 1) for v in list(obj)[:200])
        attrs = getattr(obj, "__dict__", None)
        if isinstance(attrs, dict) and level > 0:
            return any(
                walk(v, level - 1)
                for k, v in list(attrs.items())[:300]
                if not k.startswith("__") and not callable(v)
            )
        return False

    return walk(app, depth)


# -- the legs ------------------------------------------------------------------------------- #
def _photons(walk: Walk):
    from chisurf.plugins.burst.burst_selection import demo

    spc = demo.make_demo(walk.scratch / "raw")
    return demo, spc


def leg_drop_photons(walk: Walk) -> dict:
    _demo, spc = _photons(walk)
    rows = walk.drop([spc], "photons")
    row = rows[0]
    assert row.get("address"), f"the photons row has no address: {row}"
    walk.grab("photons_row")
    return {"address": row["address"], "rows": len(walk.rows())}


def leg_drop_container(walk: Walk) -> dict:
    from chisurf.core.fio.pto import Measurement

    demo, spc = _photons(walk)
    with Measurement.create(spc, title="Workspace demo") as m:
        pto = Path(m.path)
    rows = walk.drop([pto], "photons")
    walk.grab("container_rows")
    return {"container": str(pto), "photons_rows": len(rows)}


def leg_burst_chain(walk: Walk) -> dict:
    demo, spc = _photons(walk)
    photons = walk.drop([spc], "photons")
    tool = walk.feed("burst_selection", photons)
    m = getattr(tool, "model", tool)
    m.set_setup({**demo.SETUP, "setup_name": ""})
    assert m.prepare_run() is None, m.blocked_reason()
    m.run()
    walk.wait_for(lambda: m.n_bursts == demo.N_BURSTS, 300, f"{demo.N_BURSTS} bursts")
    parent = str(photons[0].get("uid"))
    runs = walk.wait_for(
        lambda: [r for r in walk.rows("bursts") if str(r.get("parent")) == parent] or None,
        120,
        "the burst run as a child row of the photons dataset",
    )
    m.gmm_components = 2
    verdict = m.write_decay()
    assert "registered" in verdict, verdict
    decay = walk.wait_for(lambda: walk.rows("decay") or None, 60, "the sub-ensemble decay row")
    panel, docks = walk.shell.data.datasets, walk.shell.data
    panel.select_dataset(decay[-1])
    models = [n for n in panel.model_names() if "lifetime" in n.lower() or "decay" in n.lower()]
    assert models, "no decay model offered for the sub-ensemble decay"
    panel.model = models[0]
    panel.add_fit()
    walk.wait_for(lambda: docks.current_uid and not docks.busy, 60, "the fit")
    assert docks.run_fit(), "the Analysis dock's Run refused"
    walk.wait_for(lambda: not docks.busy, 180, "the fit to finish")
    walk.grab("burst_chain_fit")
    return {
        "bursts": m.n_bursts,
        "runs": len(runs),
        "decay": decay[-1].get("name"),
        "model": models[0],
    }


def _feed_all(walk: Walk, tools, rows) -> dict:
    seen = {}
    for tool in tools:
        walk.feed(tool, rows)
        walk.grab(f"{tool}_fed")
        seen[tool] = "took the workspace rows"
    return seen


def leg_fcs_from_photons(walk: Walk) -> dict:
    from chisurf.plugins.fcs.fcs_correlator import demo

    path = demo.make_demo(walk.scratch / "fcs")
    paths = sorted(Path(path).iterdir()) if Path(path).is_dir() else [path]
    rows = walk.drop(paths, "photons", n=1)
    walk.feed("fcs_correlator", rows)
    walk.grab("fcs_fed")
    return {"rows": len(rows)}


def leg_trace_and_windows(walk: Walk) -> dict:
    from chisurf.plugins.tttr.intensity_trace import demo

    path = demo.make_demo(walk.scratch / "trace")
    rows = walk.drop([path], "photons")
    return _feed_all(walk, LEGS["trace_and_windows"].tools, rows)


def leg_burst_run_consumers(walk: Walk) -> dict:
    from chisurf.plugins.burst.burst_fcs_correlator import demo

    made = Path(demo.make_demo(walk.scratch / "runs"))
    container = made if made.suffix == ".pto" else next(made.rglob("*.pto"))
    walk.drop([container], "photons")
    runs = walk.wait_for(lambda: walk.rows("bursts") or None, 120, "a burst run row")
    return _feed_all(walk, LEGS["burst_run_consumers"].tools, runs[:1])


def leg_decay_tools(walk: Walk) -> dict:
    from chisurf.plugins.fluorescence_decay.lltf import demo

    files = demo.make_demo(walk.scratch / "decay")
    paths = list(files.values()) if isinstance(files, dict) else [files]
    walk.shell.data.read.experiment = "TCSPC"
    rows = walk.drop(paths[:1], "decay")
    return _feed_all(walk, LEGS["decay_tools"].tools, rows)


def leg_photon_image(walk: Walk) -> dict:
    from chisurf.plugins.microscopy.clsm import demo

    ptu = demo.make_demo(walk.scratch / "clsm")
    rows = walk.drop([ptu], "image")
    assert rows[0].get("representation") in ("photons", None), rows[0]
    return _feed_all(walk, LEGS["photon_image"].tools, rows)


def leg_intensity_image(walk: Walk) -> dict:
    from chisurf.plugins.microscopy.psf_determination import demo

    tif = demo.make_demo(walk.scratch / "psf")
    rows = walk.drop([tif], "image")
    return _feed_all(walk, LEGS["intensity_image"].tools, rows)


def leg_structure(walk: Walk) -> dict:
    from chisurf.plugins.chimol import demo

    pdb = demo.make_demo(walk.scratch / "structure")
    rows = walk.drop([pdb], "structure")
    return _feed_all(walk, LEGS["structure"].tools, rows)


def leg_setup_json(walk: Walk) -> dict:
    from chisurf.plugins.burst.burst_selection import demo

    setup = walk.scratch / "detector_setup.json"
    setup.write_text(json.dumps(demo.SETUP), encoding="utf-8")
    setups = walk.drop([setup], "setup")
    _demo, spc = _photons(walk)
    photons = walk.drop([spc], "photons")
    app = walk.feed("microtime_histogram", photons + setups)
    walk.grab("setup_used")
    detectors = sorted((getattr(getattr(app, "model", None), "setup", None) or {}).get("detectors", {}))
    assert detectors == sorted(demo.SETUP.get("detectors", {})), detectors
    return {"setup": setups[0].get("address"), "detectors": detectors}


def leg_project_link_embed(walk: Walk) -> dict:
    _demo, spc = _photons(walk)
    walk.shell.data.read.import_mode = "link"
    row = walk.drop([spc], "photons")[0]
    project = walk.scratch / "work" / "journey.cs.pto"
    walk.save_feed.append(str(project))
    assert walk.shell.project.save(save_as=True), "Save Project refused"
    walk.wait_for(lambda: project.exists(), 60, "the project file")
    assert walk.shell.project.open_path(project), "reopening the project refused"
    walk.pump(1.0)
    again = walk.wait_for(
        lambda: walk.rows("photons") or None, 60, "the photons row after reopening"
    )
    assert again[0].get("link_status") in (None, "ok", "found"), again[0]
    panel = walk.shell.data.datasets
    panel.select_dataset(again[0])
    panel.embed_selected()
    walk.wait_for(lambda: not walk.shell.data.busy, 120, "embedding")
    assert walk.shell.project.save(), "saving the embedded project refused"
    from chisurf.core.project import export_gate

    # the save runs on the session's worker; the gate reads the file it writes
    try:
        walk.wait_for(
            lambda: not export_gate.check(project), 60, "the embedded project to be written"
        )
    except AssertionError:
        raise AssertionError(
            f"the project still links data after Embed + Save: {export_gate.check(project)}"
        ) from None
    walk.grab("project_embedded")
    return {"address": row.get("address"), "project": str(project)}


def leg_locate_missing(walk: Walk) -> dict:
    hosted = walk.shell.open_plugin("project_data")
    walk.wait_for(lambda: hosted.app is not None, 60, "Project data")
    # the tool's own example: a project with one moved data file and a same-name decoy
    hosted.app.load_example()
    m = getattr(hosted.app, "model", hosted.app)

    def unresolved():
        value = m.unresolved
        return value() if callable(value) else value

    walk.wait_for(lambda: unresolved(), 60, "the demo's moved file reported missing")
    m.request_search()  # 'Search in folder...': the repair asks where to look
    walk.pump(0.5)
    return {"unresolved": len(unresolved())}


def leg_zenodo_gate(walk: Walk) -> dict:
    from chisurf.core.project import export_gate

    _demo, spc = _photons(walk)
    walk.shell.data.read.import_mode = "link"
    walk.drop([spc], "photons")
    project = walk.scratch / "work" / "linked.cs.pto"
    walk.save_feed.append(str(project))
    assert walk.shell.project.save(save_as=True), "Save Project refused"
    # the write finishes on the session's worker: wait for the file the gate reads
    gates = walk.wait_for(
        lambda: project.exists() and export_gate.check(project),
        60,
        "the export gate to flag the linked project",
    )
    assert any(g.linked for g in gates), gates
    return {"flagged": [str(g.path.name) for g in gates]}


def _run_leg(leg: str, scratch: Path) -> dict:
    walk = Walk(scratch, leg)
    record: dict = {"leg": leg, "doc": LEGS[leg].doc, "status": "running"}
    try:
        walk.start_shell()
        record["observed"] = globals()[f"leg_{leg}"](walk)
        walk.check()
        record["status"] = "passed"
    except BaseException as exc:  # noqa: BLE001 - the verdict names every outcome
        record.update(
            status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc()
        )
        try:
            walk.grab("failed")
        except BaseException:
            pass
    record["input_routes"] = walk.violations
    if walk.shell is not None:
        try:
            walk.shell.close()
        except Exception:
            pass
    return record


@pytest.mark.slow
@pytest.mark.parametrize("leg", list(_params()))
def test_workspace_journey(leg, tmp_path):
    """Run *leg* in its own process; it passes when the workflow ran from the workspace alone."""
    OUT.mkdir(parents=True, exist_ok=True)
    verdict = OUT / f"{leg}.json"
    verdict.unlink(missing_ok=True)
    env = {
        **os.environ,
        "CHISURF_SETTINGS_DIR": str(tmp_path / "settings"),
        "MMFDB_SETTINGS_DIR": str(tmp_path / "settings"),
    }
    proc = subprocess.run(
        [sys.executable, __file__, "--leg", leg, "--scratch", str(tmp_path)],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=1500,
    )
    assert verdict.is_file(), (
        f"the leg's process died without a verdict (exit {proc.returncode}):\n"
        f"{proc.stdout[-2000:]}\n{proc.stderr[-4000:]}"
    )
    record = json.loads(verdict.read_text(encoding="utf-8"))
    assert record["status"] == "passed", json.dumps(record, indent=2)[:6000]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="one workspace journey leg")
    parser.add_argument("--leg", required=True, choices=sorted(LEGS))
    parser.add_argument("--scratch", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(REPO))
    result = _run_leg(args.leg, Path(args.scratch))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.leg}.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    sys.exit(0 if result["status"] == "passed" else 1)
