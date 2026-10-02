"""The docking card's view model: inputs, run control, results and the score traces, without Qt.

The inputs and the request they build are those of the Qt tool's ``_DockingModel`` (``fret/gui/dock_tool.py``, which
cannot be imported without Qt); the run is the same: ``dock`` in a terminable child process, repeated docking through
``estimate_errors``, the other operations inline, the score traces read from the files the engine writes while it
runs. The tests compare :meth:`DockingSession.build_params` with the Qt model's for the same inputs.
"""

from __future__ import annotations

import concurrent.futures
import glob
import os
import pathlib
import threading
import time
import traceback
from typing import Any

import numpy as np

from chisurf.plugins.modelling.fret.core import stat as _stat

from .fps_model import Rows

OPERATIONS = ("dock", "refine", "screen", "score")
METHODS = ("minimize", "mc")
AV_BACKENDS = ("auto", "labellib", "imp-bff")
#: Columns of the results table, in the Qt table's order.
RESULT_KEYS = ("trial", "type", "score", "distances", "best_pdb")


def fmt_eta(seconds: float) -> str:
    """A remaining-time estimate (the fitting dialog's format)."""
    s = max(0, int(seconds))
    if s >= 3600:
        return f"ETA {s // 3600}h {(s % 3600) // 60}m"
    if s >= 60:
        return f"ETA {s // 60}m {s % 60}s"
    return f"ETA {s}s"


def _run_op_child(op: str, params: dict, queue) -> None:
    """Run one operation in a worker process and put ``(status, payload)`` on *queue*."""
    try:
        from chisurf.plugins.modelling.fret.api import operations as ops

        fn = {"dock": ops.dock, "refine": ops.refine, "screen": ops.screen, "score": ops.score}[op]
        queue.put(("ok", fn(params)))
    except Exception:  # noqa: BLE001 - the parent shows the traceback
        queue.put(("err", traceback.format_exc()))


class DockingSession:
    """Everything the docking window edits and shows."""

    def __init__(self) -> None:
        # inputs (the Qt model's attributes)
        self.pdb_files: list[str] = []
        self.fps_json = ""
        self.output_dir = ""
        self.operation = "dock"
        self.method = "minimize"
        self.score_set = ""
        self.n_frames = 500
        self.mc_steps = 10
        self.n_best = 20
        self.n_repeats = 1
        self.refine_av_cycles = 0
        self.fixed_body = 0
        self.sigma_da = 6.0
        self.ev_weight = 1.0
        self.simulated_annealing = False
        self.save_distributions = False
        self.av_backend = "auto"
        self.save_trajectory = False
        self.poses: list = []
        self.pose_score: float | None = None
        self.continue_from_poses = False
        # results
        self.status = ""
        self.status_error = False
        self.score = 0.0
        self.n_distances = 0
        self.rows = Rows()
        self.selected_row = -1
        self.curves: dict[str, tuple[list, list]] = {}
        self.preview: list[str] = []
        self.preview_index = 0
        self.structures: dict[str, Any] = {}
        # run control
        self.running = False
        self.run_op = ""
        self.stop_event = threading.Event()
        self.progress = 0.0
        self.progress_text = ""
        self._t0 = 0.0
        self._total = 1
        self._future: concurrent.futures.Future | None = None
        self._executor = concurrent.futures.ThreadPoolExecutor(1, thread_name_prefix="dock")
        self._done: list = []
        self._lock = threading.Lock()
        self.on_change = lambda: None
        self.error_detail = ""
        self.screen_ranked: list = []

    # ── inputs ────────────────────────────────────────────────────────────

    @property
    def pdb_paths(self) -> str:
        """The rigid bodies as the engine takes them: comma-joined, order = body id."""
        return ", ".join(self.pdb_files)

    def pdb_list(self) -> list[str]:
        return list(self.pdb_files)

    def add_pdbs(self, paths: list[str]) -> int:
        """Add structure files (the same file twice is allowed: a homodimer); returns how many were taken."""
        taken = [str(p) for p in paths if str(p)]
        self.pdb_files.extend(taken)
        return len(taken)

    def remove_pdb(self, index: int) -> bool:
        if 0 <= index < len(self.pdb_files):
            del self.pdb_files[index]
            return True
        return False

    def ensure_output_dir(self) -> str:
        """A blank output folder becomes ``dock_out`` next to the fps.json (or the first PDB)."""
        if self.output_dir and self.output_dir.strip():
            return self.output_dir
        anchor = self.fps_json or (self.pdb_list()[0] if self.pdb_list() else "")
        base = pathlib.Path(anchor).parent if anchor else pathlib.Path.cwd()
        self.output_dir = str(base / "dock_out")
        return self.output_dir

    def missing_input(self) -> str:
        """What a run still needs, or an empty string."""
        if not self.pdb_files:
            return "Add at least one PDB file (one per rigid body)."
        if not self.fps_json:
            return "Choose the fps.json file."
        return ""

    def build_params(self) -> tuple[str, dict]:
        """The ``api.operations`` request for the selected operation (repeated docking becomes ``errors``)."""
        op = self.operation
        if op == "dock":
            req = {
                "pdb_paths": self.pdb_list(), "fps_json": self.fps_json, "output_dir": self.output_dir,
                "n_frames": self.n_frames, "mc_steps": self.mc_steps, "n_best": self.n_best,
                "fixed_body": self.fixed_body, "sigma_da": self.sigma_da,
                "simulated_annealing": self.simulated_annealing, "score_set": self.score_set,
                "method": self.method, "refine_av_cycles": self.refine_av_cycles, "ev_weight": self.ev_weight,
                "save_distributions": self.save_distributions, "av_backend": self.av_backend,
                "save_trajectory": self.save_trajectory,
            }
            if int(self.n_repeats) > 1:
                req["n_trials"] = int(self.n_repeats)
                return "errors", req
            if self.continue_from_poses and self.poses:
                req["initial_poses"] = list(self.poses)
            return op, req
        if op == "refine":
            return op, {"pdb_paths": self.pdb_list(), "fps_json": self.fps_json, "output_dir": self.output_dir,
                        "score_set": self.score_set}
        if op == "screen":
            return op, {"pdb_inputs": self.pdb_list(), "fps_json": self.fps_json, "score_set": self.score_set,
                        "output_csv": str(pathlib.Path(self.output_dir) / "screen.csv") if self.output_dir else None}
        return op, {"pdb_paths": self.pdb_list(), "fps_json": self.fps_json, "score_set": self.score_set,
                    "mean_position_restraint": True, "sigma_da": self.sigma_da}

    def say(self, text: str, error: bool = False) -> None:
        self.status, self.status_error = text, error

    # ── project files ─────────────────────────────────────────────────────

    def load_project(self, path: str) -> bool:
        try:
            from chisurf.plugins.modelling.fret.api.project import load_docking_project

            proj = load_docking_project(path)
        except Exception as exc:  # noqa: BLE001
            self.say(f"Failed to load the project: {exc}", True)
            return False
        self.pdb_files = [str(p) for p in proj.pdb_paths if p]
        self.fps_json = proj.fps_json
        self.output_dir = proj.output_dir
        self.operation = proj.operation or "dock"
        self.method = proj.method or "minimize"
        self.score_set = proj.score_set
        p = proj.params or {}
        self.n_frames = int(p.get("n_frames", self.n_frames))
        self.mc_steps = int(p.get("mc_steps", self.mc_steps))
        self.n_best = int(p.get("n_best", self.n_best))
        self.fixed_body = int(p.get("fixed_body", self.fixed_body))
        self.sigma_da = float(p.get("sigma_da", self.sigma_da))
        self.simulated_annealing = bool(p.get("simulated_annealing", self.simulated_annealing))
        self.poses = list(proj.poses or [])
        self.pose_score = (proj.pose_meta or {}).get("score")
        self.continue_from_poses = bool(self.poses)
        name = pathlib.Path(path).name
        self.say(f"loaded {name} ({len(self.poses)} docked bodies)" if self.poses else f"loaded {name}")
        return True

    def save_project(self, path: str) -> bool:
        try:
            from chisurf.plugins.modelling.fret.api.project import save_docking_project

            save_docking_project(
                path, pdb_paths=self.pdb_list(), fps_json=self.fps_json, output_dir=self.output_dir,
                operation=self.operation, method=self.method, score_set=self.score_set,
                params={"n_frames": self.n_frames, "mc_steps": self.mc_steps, "n_best": self.n_best,
                        "fixed_body": self.fixed_body, "sigma_da": self.sigma_da,
                        "simulated_annealing": self.simulated_annealing},
                poses=self.poses or None, pose_score=self.pose_score, pose_method=self.method,
            )
        except Exception as exc:  # noqa: BLE001
            self.say(f"Failed to save the project: {exc}", True)
            return False
        self.say(f"saved {pathlib.Path(path).name}")
        return True

    # ── results ───────────────────────────────────────────────────────────

    def clear_results(self) -> None:
        self.rows = Rows()
        self.curves = {}
        self.preview = []
        self.selected_row = -1

    def sampling_kind(self) -> str:
        if self.operation == "refine":
            return "refine"
        return "dock" if self.method == "minimize" else "mc"

    def trace_name(self) -> str:
        """The per-iteration score file the chosen method writes."""
        return "convergence.csv" if self.method == "minimize" else "stat.0.out"

    def stat_files(self) -> list[str]:
        """Trace files to plot: one for a single dock, one per trial for repeats."""
        out = self.output_dir
        if not out:
            return []
        if self.run_op == "errors":
            return sorted(glob.glob(str(pathlib.Path(out) / "trial_*" / self.trace_name())))
        return [str(pathlib.Path(out) / self.trace_name())]

    def update_curves(self) -> None:
        for path in self.stat_files():
            frames, scores = _stat.read_score_series(path)
            if scores:
                self.curves[path] = (list(frames), list(scores))

    def best_score_so_far(self) -> float | None:
        best = None
        for _frames, scores in self.curves.values():
            if scores:
                best = min(scores) if best is None else min(best, min(scores))
        return best

    def add_rows(self, rows: list[tuple], kind: str) -> None:
        """Append ``(trial, score, n_distances, pdb)`` rows; runs accumulate until Clear."""
        records = list(self.rows)
        for trial, score, n_dist, pdb in rows:
            records.append({"trial": int(trial), "type": kind, "score": float(score) if score == score else float("nan"),
                            "distances": int(n_dist), "best_pdb": pathlib.Path(pdb).name if pdb else "",
                            "path": str(pdb) if pdb else ""})
        new = Rows(sorted(records, key=lambda r: (r["score"] != r["score"], r["score"])))
        new.revision = self.rows.revision + 1
        self.rows = new

    # ── run ───────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """The Run button: build the request and start the worker (a missing input is the status line's message)."""
        if self.running:
            return False
        missing = self.missing_input()
        if missing:
            self.say(missing, True)
            return False
        if self.operation in ("dock", "refine", "screen"):
            self.ensure_output_dir()
        op, params = self.build_params()
        self.say("running...")
        self.running = True
        self.run_op = op
        self.stop_event.clear()
        n_trials = max(1, int(self.n_repeats)) if op == "errors" else 1
        self._total = max(1, int(self.n_frames)) * n_trials
        out = self.output_dir
        if out:   # stale trace files would make the progress jump to 100% at once
            for path in glob.glob(str(pathlib.Path(out) / "**" / self.trace_name()), recursive=True):
                try:
                    pathlib.Path(path).unlink()
                except OSError:
                    pass
        self.curves = {}
        self.progress, self.progress_text = 0.0, "starting..."
        self._t0 = time.perf_counter()
        self._future = self._executor.submit(self._work, op, params)
        return True

    def stop(self) -> None:
        """The Cancel button of the progress bar: ask the run to stop (a docking process is terminated)."""
        self.stop_event.set()
        self.progress_text = "stopping..."

    def _work(self, op: str, params: dict) -> None:
        try:
            from chisurf.plugins.modelling.fret.api import operations as ops

            if op == "dock":
                result = self._dock_in_child(params)
                if result is None:
                    return self._push(("stopped", None))
            elif op == "errors":
                result = ops.estimate_errors(params, stop_check=self.stop_event.is_set)
            else:
                result = {"refine": ops.refine, "screen": ops.screen, "score": ops.score}[op](params)
            self._push(("ok", result))
        except Exception:  # noqa: BLE001
            self._push(("err", traceback.format_exc()))

    def _push(self, item) -> None:
        with self._lock:
            self._done.append(item)

    def _dock_in_child(self, params: dict):
        """Dock in a terminable child process (Monte-Carlo cannot be interrupted cooperatively); None when stopped."""
        import multiprocessing as mp
        import queue as _queue

        from chisurf.plugins.modelling.fret.api import operations as ops

        os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
        try:
            ctx = mp.get_context("fork")
        except ValueError:                      # no fork (Windows): inline, no cancel
            return ops.dock(params, stop_check=self.stop_event.is_set)
        q = ctx.Queue()
        proc = ctx.Process(target=_run_op_child, args=("dock", params, q), daemon=True)
        proc.start()
        while True:
            if self.stop_event.is_set():
                proc.terminate()
                proc.join(3)
                return None
            try:
                status, payload = q.get(timeout=0.2)
                break
            except _queue.Empty:
                if not proc.is_alive():
                    raise RuntimeError("Docking process exited unexpectedly.")
        proc.join(3)
        if status != "ok":
            raise RuntimeError(payload)
        return payload

    def poll(self) -> bool:
        """Take the run's progress and its result; True when something on screen changed."""
        changed = False
        if self.running:
            self.update_curves()
            done = sum(_stat.count_frames(p) for p in self.stat_files())
            if self.run_op in ("dock", "errors") and done:
                total = max(1, self._total)
                self.progress = min(done, total) / total
                parts = [fmt_eta((time.perf_counter() - self._t0) / done * (total - done))]
                best = self.best_score_so_far()
                if best is not None:
                    parts.append(f"best score {best:.1f}")
                self.progress_text = "  |  ".join(parts)
            elif self.run_op not in ("dock", "errors"):
                self.progress_text = "running..."
            changed = True
        with self._lock:
            done_items, self._done = self._done, []
        for kind, payload in done_items:
            self._finish(kind, payload)
            changed = True
        return changed

    def _finish(self, kind: str, payload) -> None:
        stopped = self.stop_event.is_set()
        self.update_curves()
        self.running = False
        self.progress = 0.0
        self.progress_text = ""
        if kind == "stopped":
            self.say("stopped")
            return
        if kind == "err":
            self.say("error: " + payload.strip().splitlines()[-1], True)
            self.error_detail = payload[-2000:]
            return
        result = payload
        data = result.get("data", {})
        self.say(result.get("status", "ok"))
        kind_name = self.sampling_kind()
        if self.run_op == "errors":
            self._finish_repeats(data, kind_name, stopped)
        elif "score" in data:
            self.score = float(data.get("score") or 0.0)
            self.n_distances = int(data.get("n_distances") or 0)
            poses = data.get("poses") or []
            if poses:
                self.poses, self.pose_score = poses, self.score
            best = (data.get("best_pdbs") or [None])[0]
            self.add_rows([(0, self.score, self.n_distances, best)], kind_name)
            traj = data.get("extra", {}).get("trajectory") or []
            frames = traj if len(traj) > 1 else (data.get("best_pdbs") or [])
            if frames:
                self.show_structures(frames)
            if stopped or data.get("extra", {}).get("stopped"):
                self.say(f"stopped (score {self.score:.1f})")
            else:
                self.say(f"{kind_name}: score {self.score:.2f} · {self.n_distances} distances")
        elif "ranked" in data:
            self.n_distances = len(data["ranked"])
            self.say(f"ranked {len(data['ranked'])} structures")
            self.screen_ranked = data["ranked"]

    def _finish_repeats(self, data: dict, kind_name: str, stopped: bool) -> None:
        """Repeated docking: one row per trial from the engine's ``trial_scores`` and ``trial_dirs``."""
        extra = data.get("extra", {})
        scores = list(extra.get("trial_scores") or [])
        dirs = list(extra.get("trial_dirs") or [])
        rows = []
        for i, score in enumerate(scores):
            pdb = os.path.join(str(dirs[i]), "docked.pdb") if i < len(dirs) else ""
            rows.append((i, score, int(data.get("n_distances") or 0), pdb if pdb and os.path.exists(pdb) else None))
        self.add_rows(rows, kind_name)
        if rows:
            self.score = float(min(scores))
            self.n_distances = int(data.get("n_distances") or 0)
        done = len(scores)
        n_trials = int(extra.get("n_trials") or done)
        head = f"stopped after {done}/{n_trials} trials" if stopped else f"{n_trials} trials"
        spread = ""
        if scores and extra.get("score_mean") is not None:
            spread = f": mean {float(extra['score_mean']):.1f} ± {float(extra.get('score_std') or 0.0):.1f}"
        unc = data.get("uncertainty") or {}
        rmsf = unc.get("mobile_rmsf_mean")
        precision = f"; precision {rmsf:.1f} Å" if rmsf == rmsf and rmsf is not None and unc.get("n_models", 0) >= 2 else ""
        self.say(head + spread + precision)
        models = [r[3] for r in rows if r[3]]
        if models:
            self.show_structures(models)

    def poll_wait(self, timeout: float = 120.0) -> bool:
        """Block until the run is finished and in (tests, headless use)."""
        end = time.monotonic() + timeout
        while self.running and time.monotonic() < end:
            time.sleep(0.02)
            self.poll()
        self.poll()
        return not self.running

    # ── structure preview ─────────────────────────────────────────────────

    def show_structures(self, paths) -> None:
        models = [str(paths)] if isinstance(paths, (str, pathlib.Path)) else [str(p) for p in paths or []]
        if models != self.preview:
            self.preview = models
            self.preview_index = 0

    def select_row(self, index: int) -> None:
        self.selected_row = index
        if 0 <= index < len(self.rows) and self.rows[index].get("path"):
            self.show_structures(self.rows[index]["path"])

    def backbone(self, path: str):
        """The CA / P trace of a structure file, or None."""
        if not path or not os.path.isfile(path):
            return None
        if path not in self.structures:
            try:
                import chisurf.core.structure as cs_structure

                self.structures[path] = cs_structure.Structure(path)
            except Exception:  # noqa: BLE001
                self.structures[path] = None
        struct = self.structures[path]
        if struct is None or struct.atoms is None:
            return None
        atoms = struct.atoms
        keep = np.isin(atoms["atom_name"], ["CA", "P"])
        return np.asarray(atoms["xyz"])[keep], np.asarray(atoms["chain"])[keep]

    # ── persistence ───────────────────────────────────────────────────────

    FIELDS = ("pdb_files", "fps_json", "output_dir", "operation", "method", "score_set", "n_frames", "mc_steps",
              "n_best", "n_repeats", "refine_av_cycles", "fixed_body", "sigma_da", "ev_weight",
              "simulated_annealing", "save_distributions", "av_backend", "save_trajectory", "continue_from_poses")

    def export_settings(self) -> dict:
        state = {name: getattr(self, name) for name in self.FIELDS}
        state["pdb_files"] = list(self.pdb_files)
        return state

    def restore_settings(self, settings: dict) -> None:
        if not isinstance(settings, dict):
            return
        for name in self.FIELDS:
            if name not in settings:
                continue
            value, current = settings[name], getattr(self, name)
            if name == "pdb_files":
                if isinstance(value, list):
                    self.pdb_files = [str(v) for v in value]
            elif name == "operation":
                if value in OPERATIONS:
                    self.operation = value
            elif name == "method":
                if value in METHODS:
                    self.method = value
            elif name == "av_backend":
                if value in AV_BACKENDS:
                    self.av_backend = value
            elif isinstance(current, bool):
                if isinstance(value, bool):
                    setattr(self, name, value)
            elif isinstance(current, int):
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    setattr(self, name, int(value))
            elif isinstance(current, float):
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    setattr(self, name, float(value))
            elif isinstance(current, str) and isinstance(value, str):
                setattr(self, name, value)

    def close(self) -> None:
        self.stop_event.set()
        self._executor.shutdown(wait=False, cancel_futures=True)


__all__ = ["AV_BACKENDS", "DockingSession", "METHODS", "OPERATIONS", "RESULT_KEYS", "fmt_eta"]
