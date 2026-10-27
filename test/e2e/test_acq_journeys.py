"""Acquisition-driven journeys: every leg starts in the Record tool and continues in the UI.

Each leg opens the Record tool in a real shell, sets it up and starts a simulated measurement
through the tool's own controls (the clicks a user makes: Mode, Load example, Start), waits for the
recording to land in the Datasets workspace, and then hands the recorded dataset to the analysis
tools the way a user does (*Open in…* / a drag: ``EmtkShellApp.feed_from_workspace``), presses each
tool's own run control and checks the result -- against the simulation's truth where there is one
(FRC resolution against the simulated focus, burst E populations, lifetimes, FCS diffusion time).

The run length and speed are model settings (typing numbers into fields is not what the leg
tests); everything a workflow decides is a click. An input file dialog opened anywhere fails the
leg (the guard of :mod:`test.e2e.test_workspace_journeys`). Each leg runs in its own process and
writes a verdict JSON and a PNG per step under ``test/e2e/acq_journeys/<leg>/``.
"""

from __future__ import annotations

import json
import re
import os
import subprocess
import sys
import time
import traceback
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "acq_journeys"

#: Names of the control that starts a tool's analysis, in order of preference.
RUN_CONTROLS = (
    "toolAction_run", "request_run", "measure", "run_maps", "run_coloc", "map_flow", "track", "compute", "run", "run_search",
    "search", "find", "find_spots", "fit", "run_fit", "analyse", "analyze", "correlate", "apply",
    "start", "process", "calculate", "estimate", "request_estimate", "Run", "Detect", "Fit",
)  # fmt: skip

#: Tools whose analysis is several presses, in order (PSF: find the beads, then fit them all).
RUN_SEQUENCES = {"psf_determination": ("detect_beads", "fit_all")}


#: Captions of controls whose label is not their name (pressed by caption when the registry
#: rectangle is local to an inner dock).
CAPTIONS = {"toolAction_run": "Run", "run_maps": "Run",
            "compute": "Compute"}  # fmt: skip


@dataclass
class Leg:
    doc: str
    mode: str  # the Record tool's Mode caption
    tools: tuple[str, ...] = ()


LEGS: dict[str, Leg] = {
    "image_frc": Leg("the owner's path: simulated scan -> Datasets -> FRC", "Image (scan)"),
    "image_tools": Leg(
        "simulated scan -> every imaging tool",
        "Image (scan)",
        (
            "img_pixel_intensity", "img_pixel_micro_time", "img_pixel_phasor", "img_pixel_nb",
            "img_pixel_mle", "img_coloc", "img_drift", "img_flow", "img_tracking", "spot_finder",
            "region_mle", "psf_determination", "img_calibration",
        ),
    ),  # fmt: skip
    "smfret_pie": Leg(
        "PIE smFRET recording -> burst search -> burst consumers",
        "Point (smFRET)",
        ("burst_bva", "burst_mle_analysis", "burst_h2mm", "burst_2cde", "ndxplorer"),
    ),
    "smfret_two_color": Leg("two-colour recording -> burst search -> PR histogram", "Point (smFRET)"),
    "lifetime": Leg(
        "recording -> microtime histogram -> decay tools",
        "Point (smFRET)",
        ("lltf", "maxent_decay", "irf_estimator"),
    ),
    "fret_check": Leg("PIE recording -> FRET check", "Point (smFRET)", ("fret_check",)),
    "project_roundtrip": Leg("a recording and its runs survive save + reopen", "Point (smFRET)"),
    "fcs": Leg("FCS recording -> correlator -> correlation in Datasets -> FCS fit (truth D, N)",
               "FCS (point)"),
    "fcs_pch": Leg("FCS recording -> PCH", "FCS (point)", ("pch",)),
}


def _wj():
    """The workspace-journeys harness (guard, shell, feeding)."""
    from test.e2e import test_workspace_journeys as wj

    return wj


def registries(obj, depth: int = 3):
    """Every named-rectangle registry a hosted tool draws into (form.rects, item_rects, …)."""
    seen: set[int] = set()

    def walk(o, level):
        if o is None or id(o) in seen or level < 0:
            return
        seen.add(id(o))
        for name in ("item_rects", "_item_rects", "rects", "remember"):
            reg = getattr(o, name, None)
            if isinstance(reg, MutableMapping):
                yield reg
        if level and hasattr(o, "__dict__"):
            for key, value in list(vars(o).items())[:200]:
                if key in ("model", "session", "shell") or key.startswith("__"):
                    continue
                if hasattr(value, "__dict__") and not isinstance(value, type):
                    yield from walk(value, level - 1)

    yield from walk(obj, depth)


class AcqWalk:
    """A shell with the Record tool open; clicks go through the shell's event path."""

    def __init__(self, scratch: Path, leg: str) -> None:
        wj = _wj()
        self.walk = wj.Walk(scratch, leg)
        self.walk.out = OUT / leg
        self.leg = leg
        self.steps: list[dict] = []
        self.rec = None

    # plumbing -------------------------------------------------------------------------------- #
    @property
    def shell(self):
        return self.walk.shell

    def start(self) -> None:
        self.walk.start_shell()

    def pump(self, s: float) -> None:
        self.walk.pump(s)

    def step(self, name: str, **facts) -> None:
        self.walk.grab(f"{len(self.steps):02d}_{name}")
        self.steps.append({"step": name, **facts})

    def origin(self, app) -> tuple[float, float]:
        """Where the shell draws *app*: its dock window's content corner (form rects are local)."""
        hosted = next((h for h in self.shell.hosted.values() if h.app is app), None)
        assert hosted is not None, "the tool is not hosted in the shell"
        window = self.shell.docks.windows.get(hosted.key)
        box = getattr(window, "content", None) or getattr(window, "box", None)
        assert box is not None, f"{hosted.key} has no drawn content box"
        return float(box[0]), float(box[1])

    def rect(self, app, name: str):
        """*name*'s rectangle in shell coordinates, or ``None`` when it is not drawn."""
        self.pump(0.2)
        ox, oy = self.origin(app)
        for reg in registries(app):
            box = reg.get(name)
            if box is not None:
                x, y, w, h = (float(v) for v in box)
                return (x + ox, y + oy, w, h)
        return None

    def texts(self) -> list[tuple[str, tuple]]:
        self.walk.driver.frame(1)
        return [(str(e[5]), tuple(e[:4])) for e in self.walk.driver.painter.texts]

    def press(self, caption: str, *, region=None, last: bool = True) -> None:
        """Click the drawn caption containing *caption* (what the user sees), inside *region*."""
        def label(text: str) -> bool:  # the whole label, allowing a leading icon ("▶ Start")
            text = text.strip()
            return text == caption or (text.endswith(caption) and len(text) - len(caption) <= 4)

        hits = [b for t, b in self.texts() if label(t)]
        bottom = self.walk.driver.size[1] - 200  # below this a dock's content is scrolled away
        if hits and min(b[1] for b in hits) > bottom:
            hits = self._scroll_into_view(caption, label, hits, bottom)
        if region is not None:
            rx, ry, rw, rh = region
            hits = [b for b in hits if rx <= b[0] <= rx + rw and ry <= b[1] <= ry + rh]
        assert hits, f"{caption!r} is not drawn; drawn: {[t for t, _ in self.texts()][:80]}"
        self.walk.driver.click(hits[-1] if last else hits[0])
        self.pump(0.3)

    def names(self, app) -> list[str]:
        out: set[str] = set()
        for reg in registries(app):
            out |= {str(k) for k in reg}
        return sorted(out)

    def click(self, app, name: str) -> None:
        """Click *name* of a hosted tool where the shell drew it (a real pointer event).

        The registry rectangle is translated by the tool's dock content corner and used only when
        a caption is drawn inside it (a tool drawing nested docks keeps rectangles local to an
        inner dock); otherwise the button is pressed by its caption, as a user finds it.
        """
        box = self.rect(app, name)
        assert box is not None, f"{name!r} is not drawn; drawn: {self.names(app)[:60]}"
        x, y, w, h = box
        inside = [t for t, b in self.texts() if x - 2 <= b[0] <= x + w and y - 2 <= b[1] <= y + h]
        if inside:
            self.walk.driver.click(box)
        else:
            self.press(CAPTIONS.get(name, name.replace("_", " ").capitalize()))
        self.pump(0.3)

    def _scroll_into_view(self, caption, label, hits, bottom):
        """Wheel over the caption's dock (as a user scrolls) until it is drawn above *bottom*."""
        x = hits[-1][0] + 5
        for dy in (-3.0, 3.0):
            for _ in range(25):
                self.walk.driver.wheel(dy, at=(x, bottom - 40))
                self.pump(0.05)
                now = [b for t, b in self.texts() if label(t)]
                if now and min(b[1] for b in now) <= bottom:
                    return now
                if now and min(b[1] for b in now) > min(b[1] for b in hits) + 1:
                    break  # the wrong way
        raise AssertionError(f"{caption!r} could not be scrolled into view")

    def choose(self, current: str, caption: str) -> None:
        """Open the choice showing *current* and click its item *caption* (both as drawn)."""
        self.press(current, last=False)
        self.press(caption)

    # the Record tool ----------------------------------------------------------------------------- #
    def open_record_tool(self):
        hosted = self.shell.open_plugin("acq")
        self.walk.wait_for(lambda: hosted.app is not None, 120, "the Record tool")
        assert not hosted.error, hosted.error
        self.rec = hosted.app
        self.pump(0.5)
        return self.rec

    def record(self, mode: str, *, duration_s: float, speed: float = 50.0, setup=None) -> dict:
        """Mode -> Load example -> Start in the UI; wait for the recording's row in Datasets."""
        rec = self.rec or self.open_record_tool()
        model = rec.model
        current = dict(model.mode_options()).get(model.mode, "")
        if current != mode:
            self.choose(current, mode)
            self.walk.wait_for(lambda: dict(model.mode_options()).get(model.mode) == mode, 10,
                               f"Mode {mode!r}")
        self.press("Load example")
        if setup is not None:
            setup(model)  # documented per-leg model settings (e.g. the simulator scheme)
        model.duration_s, model.speed = float(duration_s), float(speed)
        before = {str(r.get("uid")) for r in self.walk.rows()}
        self.press("Start")  # the Acquisition dock's Start (drawn after the run bar's)
        assert model.running, f"Start did not start: {model.status_text} {model.status_detail}"
        self.walk.wait_for(lambda: not model.running, 600, "the recording to end")
        model.poll(force=True)
        name = Path(str(model.saved_path)).name
        row = self.walk.wait_for(
            lambda: next(
                (
                    r
                    for r in self.walk.rows()
                    if str(r.get("uid")) not in before and r.get("name") == name
                ),
                None,
            ),
            120,
            f"{name} in Datasets",
        )
        self.walk.show_workspace()
        self.step("recorded", row={k: row.get(k) for k in ("name", "kind", "representation",
                                                           "experiment", "embedded")})  # fmt: skip
        assert row.get("embedded"), "a fresh recording is embedded in the project"
        return row

    # tools ------------------------------------------------------------------------------------- #
    def offered(self, rows) -> list[str]:
        return [pid for pid, _ in self.shell.tools_for_rows(rows)]

    def feed(self, plugin_id: str, rows):
        assert plugin_id in self.offered(rows), (
            f"'Open in…' does not offer {plugin_id} for {[r.get('kind') for r in rows]}: "
            f"{self.offered(rows)}"
        )
        return self.walk.feed(plugin_id, rows)

    def busy(self, app) -> bool:
        children = list((getattr(app, "children", None) or {}).values())  # a hub's steps
        for obj in (app, getattr(app, "model", None), getattr(app, "controller", None), *children):
            for attr in ("busy", "running", "is_running", "computing", "working"):
                value = getattr(obj, attr, None)
                try:
                    if callable(value):
                        value = value()
                except Exception:  # noqa: BLE001 - not a flag
                    continue
                if isinstance(value, bool) and value:
                    return True
        return False

    def run_tool(self, plugin_id: str, app, *, timeout: float = 600) -> str:
        """Press the tool's run control and wait for it; returns the control's name."""
        drawn = set(self.names(app))
        sequence = RUN_SEQUENCES.get(plugin_id)
        if sequence is None:
            control = next((c for c in RUN_CONTROLS if c in drawn), None)
            assert control, (
                f"{plugin_id}: no run control among {RUN_CONTROLS}; drawn: {sorted(drawn)}"
            )
            sequence = (control,)
        for control in sequence:
            self.click(app, control)
            self.pump(1.0)
            self.walk.wait_for(lambda: not self.busy(app), timeout, f"{plugin_id} to finish")
            self.pump(0.5)
        control = "+".join(sequence)
        status = " ".join(
            str(getattr(o, a, ""))
            for o in (app, getattr(app, "model", None))
            for a in ("status", "status_line", "status_text", "error")
        )
        assert not any(w in status.lower() for w in ("failed", "traceback", "error:")), (
            f"{plugin_id}: {status}"
        )
        # what the user reads: an error line the tool drew (its whole text, not the clipped one)
        shown = [t for t, _ in self.texts() if t.strip().lower().startswith("error")]
        errors = [
            str(v) for o in (app, getattr(app, "model", None)) for a in ("error", "last_error")
            if (v := getattr(o, a, None))
        ]  # fmt: skip
        assert not shown, f"{plugin_id} shows an error: {shown[:3]} {errors[:3]}"
        return control


# -- the legs -------------------------------------------------------------------------------- #
def _image_row(w: AcqWalk) -> dict:
    row = w.record("Image (scan)", duration_s=60.0, speed=50.0)
    assert row.get("kind") == "image" and row.get("representation") == "photons", row
    assert row.get("experiment") == "Imaging", row
    return row


def leg_image_frc(w: AcqWalk) -> dict:
    row = _image_row(w)
    frc = w.feed("img_frc", [row])
    w.step("frc_fed")
    w.run_tool("img_frc", frc)
    result = frc.model.result
    w.step("frc_measured", status=frc.model.status_line)
    assert result is not None and result.crossed, frc.model.status_line
    # truth: the simulator's focus (1/e^2 radius 0.25 um) has an FWHM of ~0.29 um; a 1/7 FRC
    # resolution of a bead image is of that order.
    assert result.unit == "nm", "the pixel size comes from the recording's header"
    assert 150.0 < result.resolution < 700.0, result.resolution
    return {"resolution_nm": float(result.resolution)}


def leg_image_tools(w: AcqWalk) -> dict:
    row = _image_row(w)
    done, failed, psf = {}, {}, {}
    for pid in LEGS["image_tools"].tools:
        try:
            app = w.feed(pid, [row])
            done[pid] = w.run_tool(pid, app)
            w.step(f"{pid}_done")
            if pid == "psf_determination":
                psf = _psf_truth(app)
        except AssertionError as exc:
            failed[pid] = str(exc)[:800]
            w.step(f"{pid}_failed")
    assert not failed, json.dumps(failed, indent=1)
    return {"ran": done, "psf": psf}


def _psf_truth(app) -> dict:
    """The beads' fitted lateral FWHM against the simulated focus (1/e^2 radius 0.25 um, FWHM
    ~294 nm), in the 100 nm pixels of the example scan; a bead of finite size only widens it."""
    model = app.model
    text = str(getattr(model, "results_text", ""))
    fwhm = [float(v) for v in re.findall(r"FWHMxy\D{1,3}?([0-9]+(?:\.[0-9]+)?) nm", text)]
    out = {"beads": len(getattr(model, "detected_beads", []) or []), "summary": text[:300]}
    assert fwhm, f"no lateral FWHM in the PSF report: {text[:300]}"
    # beads closer than a ROI are fitted as one wide spot: the narrowest is an isolated bead
    out["fwhm_xy_nm"] = sorted(fwhm)
    assert 230.0 < min(fwhm) < 380.0, out
    assert out["beads"] >= 1, out
    return out


def _burst_runs(w: AcqWalk, photons_row: dict) -> list[dict]:
    uid = str(photons_row.get("uid"))
    return [r for r in w.walk.rows("bursts") if str(r.get("parent")) == uid]


def _search(w: AcqWalk, row: dict) -> dict:
    before = {str(r.get("uid")) for r in _burst_runs(w, row)}
    sel = w.feed("burst_selection", [row])
    w.run_tool("burst_selection", sel)
    run = w.walk.wait_for(
        lambda: next(
            (r for r in _burst_runs(w, row) if str(r.get("uid")) not in before), None
        ),
        300,
        "the burst run as a child of the recording",
    )
    w.walk.show_workspace()  # the run is listed at once, a child of its recording
    w.step("burst_search", run=run.get("name"))
    return run


def _proximity(run_row: dict, photons_row: dict, *, pie: bool) -> np.ndarray:
    """Each burst's raw proximity ratio, red / (green + red) under donor excitation, counted
    from the recording's photons between the run's First and Last Photon -- the burst search
    is judged against the simulated E without a downstream tool in the way."""
    import tttrlib
    from ndxplorer.io import pto_reader

    from chisurf.core.plugin.workspace_input import read_address

    address = str(run_row.get("address"))
    container, _, _run = address.partition(".pto/")
    store, _ = pto_reader.read_run(container + ".pto")  # the newest search: the one just run
    first = np.asarray(store.column_by_name("First Photon"), dtype=np.int64)
    last = np.asarray(store.column_by_name("Last Photon"), dtype=np.int64)
    tttr = tttrlib.TTTR(read_address(str(photons_row.get("address"))))
    channel = np.asarray(tttr.routing_channels, dtype=np.int64)
    micro = np.asarray(tttr.micro_times, dtype=np.int64)
    # PIE: the donor's pulse is the first half of the period (the simulator's prompt window)
    donor_excited = micro < (micro.max() + 1) // 2 if pie else np.ones(micro.size, bool)
    green = np.cumsum(np.r_[0, (channel == 0) & donor_excited])
    red = np.cumsum(np.r_[0, (channel == 1) & donor_excited])
    n_green = green[last + 1] - green[first]
    n_red = red[last + 1] - red[first]
    total = n_green + n_red
    return np.where(total > 0, n_red / np.maximum(total, 1), np.nan)


def _two_populations(pr: np.ndarray, low: float, high: float, tol: float = 0.12) -> dict:
    pr = pr[np.isfinite(pr) & (pr > -0.1) & (pr < 1.1)]
    assert pr.size > 50, f"only {pr.size} bursts"
    a, b = np.quantile(pr, 0.25), np.quantile(pr, 0.75)
    for _ in range(20):  # two-means
        near_a = np.abs(pr - a) < np.abs(pr - b)
        a, b = pr[near_a].mean(), pr[~near_a].mean()
    lo, hi = sorted((a, b))
    assert abs(lo - low) < tol and abs(hi - high) < tol, (lo, hi)
    return {"pr_low": float(lo), "pr_high": float(hi), "bursts": int(pr.size)}


def _container_writes() -> list:
    """Every container write the shared notification reports (the Datasets view's refresh)."""
    from chisurf.core.project import analysis

    writes: list = []
    analysis.on_container_changed(writes.append)
    return writes


def leg_smfret_pie(w: AcqWalk) -> dict:
    row = w.record("Point (smFRET)", duration_s=60.0, speed=50.0)
    writes = _container_writes()
    run = _search(w, row)
    assert writes, "the burst search wrote its run without the container-changed notification"
    # truth: E 0.2 / 0.8 (realistic crosstalk lifts the raw low population a little)
    science = _two_populations(_proximity(run, row, pie=True), 0.25, 0.78)
    ran, failed = {}, {}
    for pid in LEGS["smfret_pie"].tools:
        try:
            app = w.feed(pid, [run])
            n0 = len(writes)
            ran[pid] = w.run_tool(pid, app) if pid != "ndxplorer" else "opened"
            w.walk.show_workspace()  # a companion table is in the run at once
            w.step(f"{pid}_done", container_writes=len(writes) - n0)
        except AssertionError as exc:
            failed[pid] = str(exc)[:800]
            w.step(f"{pid}_failed")
    assert not failed, json.dumps(failed, indent=1)
    return {**science, "ran": ran, "container_writes": [str(p) for p in writes]}


def leg_smfret_two_color(w: AcqWalk) -> dict:
    def two_color(model):
        model.sim_scheme = "two_color"

    row = w.record("Point (smFRET)", duration_s=60.0, speed=50.0, setup=two_color)
    run = _search(w, row)
    return _two_populations(_proximity(run, row, pie=False), 0.25, 0.78)


def leg_fret_check(w: AcqWalk) -> dict:
    row = w.record("Point (smFRET)", duration_s=40.0, speed=50.0)
    app = w.feed("fret_check", [row])
    # FRET check analyses what it is given at once; its result is drawn as "analysed"
    w.walk.wait_for(lambda: "analysed" in w.names(app), 600, "FRET check's analysis")
    w.step("fret_check_done")
    return {}


def leg_lifetime(w: AcqWalk) -> dict:
    row = w.record("Point (smFRET)", duration_s=40.0, speed=50.0)
    before = {str(r.get("uid")) for r in w.walk.rows()}
    hist = w.feed("microtime_histogram", [row])
    w.run_tool("microtime_histogram", hist)
    w.step("histogram")
    # Save writes the decay (Output is a text field, set through the model) and, in a workspace,
    # adds it to Datasets as a child of the recording
    hist.model.output = str(w.walk.scratch / "decay.dat")
    w.press("Save")
    decays = w.walk.wait_for(
        lambda: [r for r in w.walk.rows("decay") if str(r.get("uid")) not in before],
        120,
        "a decay row from the microtime histogram",
    )
    ran = {}
    for pid in LEGS["lifetime"].tools:
        app = w.feed(pid, decays[:1])
        ran[pid] = w.run_tool(pid, app)
        w.step(f"{pid}_done")
    return {"ran": ran}


def leg_project_roundtrip(w: AcqWalk) -> dict:
    row = w.record("Point (smFRET)", duration_s=30.0, speed=50.0)
    run = _search(w, row)
    project = w.shell.project
    saved = w.walk.scratch / "acq_roundtrip.cs.pto"
    # Save Project as… answers its save dialog with this path (the harness's save feed: a
    # save dialog is the user's choice of a new file, not an input file dialog)
    w.walk.save_feed.append(str(saved))
    assert project.save(save_as=True), "Save Project refused"
    w.walk.wait_for(lambda: not project.busy and saved.is_file(), 120, "the save")
    assert project.open_path(saved)
    w.walk.wait_for(
        lambda: not project.busy and any(r.get("name") == row.get("name") for r in w.walk.rows()),
        120,
        "the reopened recording",
    )
    w.walk.wait_for(
        lambda: any(r.get("name") == run.get("name") for r in w.walk.rows("bursts")),
        120,
        "the reopened burst run",
    )
    w.step("reopened")
    return {"saved": str(saved)}


#: The shell's FCS model the fit uses (the one the FCS demo fits).
FCS_MODEL = "FCS (general: diffusion + bunching/anticorr)"


def _fcs_recording(w: AcqWalk, seconds: float = 20.0) -> tuple[dict, dict]:
    row = w.record("FCS (point)", duration_s=seconds, speed=50.0)
    truth = dict(getattr(w.rec.model.session, "truth", {}) or {})
    assert truth, "the simulated FCS sample states its truth"
    return row, truth


def leg_fcs(w: AcqWalk) -> dict:
    row, truth = _fcs_recording(w)
    before = {str(r.get("uid")) for r in w.walk.rows()}
    corr = w.feed("fcs_correlator", [row])
    w.step("correlator_files", sources=list(getattr(corr.ensure_child("files"),
                                                   "source_datasets", []) or []))  # fmt: skip
    w.press("4. Correlator")  # the hub's step list
    w.press("Correlate")
    w.pump(1.0)
    w.walk.wait_for(lambda: not w.busy(corr), 600, "the correlation")
    curve = w.walk.wait_for(
        lambda: next(
            (
                r
                for r in w.walk.rows()
                if str(r.get("uid")) not in before and str(r.get("parent")) == str(row.get("uid"))
            ),
            None,
        ),
        120,
        "the correlation in Datasets (a child of the recording): rows "
        + str([(r.get("name"), r.get("parent")) for r in w.walk.rows()])
        + " sources " + str(getattr(corr.ensure_child("files"), "source_datasets", None))
        + " source_of " + str(corr._correlation_source()),
    )
    w.step("correlated", curve={k: curve.get(k) for k in ("name", "kind", "experiment")})
    data = w.shell.data
    w.walk.show_workspace()
    # select the row as the table does (the datasets list's row, not the drawn tree's copy)
    listed = next(r for r in data.datasets.datasets if str(r.get("uid")) == str(curve.get("uid")))
    data.datasets.select_dataset(listed)
    w.pump(0.5)
    assert FCS_MODEL in data.datasets.model_names(), data.datasets.model_names()
    data.datasets.model = FCS_MODEL
    w.walk.driver.click("datasets.add_fit")
    w.walk.wait_for(lambda: data.windows and data.analysis.info, 120,
                    "the fit window: " + str(getattr(w.shell, "status", "")))
    # The focus calibration is known, as it is at the instrument (a dye of known D calibrates
    # it): w_r and w_z are set to the simulated focus and fixed in the parameter table (set
    # through its model -- numeric cells -- as a user types them). Left free, w_z collapses onto
    # w_r and D runs off with it (N 6.8, D 12 on a 20 s run).
    for name, value in (("w_r", truth["w0_um"] * 1e3), ("w_z", truth["z0_um"] * 1e3)):
        record = next(r for r in data.analysis.parameters if r["name"] == name)
        data.analysis.edit_parameter(record, "value", value)
        w.pump(0.3)
        record = next(r for r in data.analysis.parameters if r["name"] == name)
        data.analysis.edit_parameter(record, "fixed", True)
        w.walk.wait_for(
            lambda n=name, v=value: any(
                r["name"] == n and r.get("fixed") and abs(float(r["value"]) - v) < 1e-6
                for r in data.analysis.parameters
            ),
            60,
            f"{name} = {value:g} nm, fixed",
        )
    # The fit starts past the detector dead time, as a user sets First: the lags below ~1 us
    # are the dead-time dip (G ~ 0.15 at 10-30 ns), not diffusion, and fitted they pull N up
    # and D down (N 6.7, D 28 with the focus fixed).
    from chisurf.core.api import dataset_objects

    dataset = next(
        d for d in dataset_objects()
        if getattr(d, "experiment", None) is not None and str(getattr(d, "name", "")) == curve["name"]
        or str(getattr(d, "uid", "")) == str(curve["uid"])
    )  # fmt: skip
    lags_ms = np.asarray(dataset.x, dtype=float)
    first = int(np.argmax(lags_ms >= 1e-3))
    data.analysis.xmin = first
    data.analysis.range_changed()
    w.walk.wait_for(lambda: data.analysis.xmin == first and not data.busy, 60, "the fit range")
    w.step("calibrated", w_r_nm=truth["w0_um"] * 1e3, w_z_nm=truth["z0_um"] * 1e3,
           first_lag_ms=float(lags_ms[first]))  # fmt: skip
    chi2_before = data.analysis.info.get("chi2r_current")
    w.walk.driver.click("analysis.run_fit")
    w.walk.wait_for(
        lambda: not data.busy and data.analysis.info.get("chi2r_current") != chi2_before,
        300,
        "the FCS fit",
    )
    params = {r["name"]: r["value"] for r in data.analysis.parameters}
    w.step("fitted", parameters={k: v for k, v in params.items() if isinstance(v, (int, float))})
    n_fit = float(params["N"])
    # the model is written in D (um^2/s) and the lateral waist w_r (nm): tau_D = w_r^2 / 4D
    w_r_um, d_fit = float(params["w_r"]) * 1e-3, float(params["D"])
    td_fit_s = w_r_um * w_r_um / (4.0 * d_fit)
    # Truth: N and tau_D from the simulator's focus and box. The simulator's 0.1 um focus grid
    # widens the 0.3 um waist to ~0.33 um, so tau_D comes out ~18 % long (measured on 20 s runs);
    # 35 % covers it plus the statistics of a short run.
    assert abs(n_fit / truth["n"] - 1.0) < 0.35, (n_fit, truth)
    assert abs(td_fit_s / truth["tau_d_s"] - 1.0) < 0.35, (td_fit_s, truth)
    return {"n_fit": n_fit, "tau_d_fit_s": td_fit_s, "d_fit": d_fit, "w_r_um": w_r_um,
            "truth": truth}


def leg_fcs_pch(w: AcqWalk) -> dict:
    row, truth = _fcs_recording(w, seconds=10.0)
    app = w.feed("pch", [row])
    control = w.run_tool("pch", app)
    w.step("pch_done")
    return {"control": control, "truth_n": truth["n"]}


# -- running a leg ----------------------------------------------------------------------------- #
def _run_leg(leg: str, scratch: Path) -> dict:
    w = AcqWalk(scratch, leg)
    record: dict = {"leg": leg, "doc": LEGS[leg].doc, "status": "running"}
    try:
        w.start()
        w.open_record_tool()
        record["observed"] = globals()[f"leg_{leg}"](w)
        w.walk.check()
        record["status"] = "passed"
    except BaseException as exc:  # noqa: BLE001 - the verdict names every outcome
        record.update(
            status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc()
        )
        try:
            w.walk.grab("failed")
        except BaseException:
            pass
    record["steps"] = w.steps
    record["input_routes"] = w.walk.violations
    if w.shell is not None:
        try:
            w.shell.close()
        except Exception:
            pass
    return record


@pytest.mark.slow
@pytest.mark.parametrize("leg", list(LEGS))
def test_acq_journey(leg, tmp_path):
    """Run *leg* in its own process; it passes when the workflow ran from the recording alone."""
    OUT.mkdir(parents=True, exist_ok=True)
    verdict = OUT / f"{leg}.json"
    verdict.unlink(missing_ok=True)
    env = {
        **os.environ,
        "CHISURF_SETTINGS_DIR": str(tmp_path / "settings"),
        "MMFDB_SETTINGS_DIR": str(tmp_path / "settings"),
        "CHISURF_PROJECT_TEMP_DIR": str(tmp_path / "projects"),
    }
    proc = subprocess.run(
        [sys.executable, __file__, "--leg", leg, "--scratch", str(tmp_path)],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=2400,
    )
    assert verdict.is_file(), (
        f"the leg's process died without a verdict (exit {proc.returncode}):\n"
        f"{proc.stdout[-2000:]}\n{proc.stderr[-4000:]}"
    )
    result = json.loads(verdict.read_text(encoding="utf-8"))
    assert result["status"] == "passed", json.dumps(result, indent=2)[:6000]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="one acquisition journey leg")
    parser.add_argument("--leg", required=True, choices=sorted(LEGS))
    parser.add_argument("--scratch", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(REPO))
    started = time.monotonic()
    result = _run_leg(args.leg, Path(args.scratch))
    result["seconds"] = round(time.monotonic() - started, 1)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.leg}.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    sys.exit(0 if result["status"] == "passed" else 1)
