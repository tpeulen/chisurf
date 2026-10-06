"""Portable LLTF command, configuration, process and result workflow.

:class:`LLTFModel` is also the model the emtk app's view spec (``lltf.view.json``)
draws: its fields are the spec's attrs, :meth:`enabled` greys what the Qt wizard
greyed, :meth:`lifetime_rows` / :meth:`results_summary` feed the Results panel.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np
import yaml

from ..core.settings import get_default_settings

MODULE = "chisurf.plugins.fluorescence_decay.lltf.core"


class LLTFModel:
    """State, command, subprocess and result of one LLTF fit (no GUI)."""

    def __init__(self):
        self.decay_file = ""
        self.irf_file = ""
        self.config_file = ""
        self.output_dir = ""
        self.output_file = ""
        self.n_lifetimes = 1
        self.find_optimal = False
        self.max_lifetimes = 4
        self.prob_threshold = 0.68
        self.verbose = True
        self.config_text = yaml.safe_dump(get_default_settings(), sort_keys=False)
        self.config_dirty = False
        self.loaded_config_file = ""
        self.process = None
        self.output = []
        self.returncode = None
        self.result = None
        self.status = "Load decay and IRF files, configure the fit, then run analysis."
        self._queue = queue.Queue()
        self._reader = None
        self._workspace = None

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    # ── view-spec hooks ───────────────────────────────────────────────────
    def enabled(self, name):
        """What the Qt wizard greyed: the fixed count under a search, the search's limits without one."""
        if self.running:
            return False
        if name == "n_lifetimes":
            return not self.find_optimal
        if name in ("max_lifetimes", "prob_threshold"):
            return bool(self.find_optimal)
        return True

    def lifetime_rows(self):
        """The fitted components, as the Qt results table listed them."""
        return [
            {
                "component": index + 1,
                "amplitude": float(row["amplitude"]),
                "lifetime": float(row["lifetime"]),
            }
            for index, row in enumerate((self.result or {}).get("lifetimes", []))
        ]

    def results_summary(self):
        """The lines under the Qt results table: χ², χ²ᵣ, the time range and the component count."""
        result = self.result
        if not result:
            return "Run an analysis to obtain fit results."
        lines = []
        if "chi_square" in result:
            lines.append(f"Chi-square: {result['chi_square']:.3f}")
        if "reduced_chi_square" in result:
            lines.append(f"Reduced chi-square: {result['reduced_chi_square']:.3f}")
        if "time_range" in result:
            lines.append(
                f"Time range: {result['time_range']['start']:.3f} - {result['time_range']['stop']:.3f} ns"
            )
        if "n_lifetimes" in result:
            lines.append(f"Number of lifetimes: {result['n_lifetimes']}")
        return "\n".join(lines)

    def load_config(self, path):
        text = Path(path).read_text()
        if not isinstance(yaml.safe_load(text), dict):
            raise ValueError("LLTF configuration must be a YAML mapping.")
        self.config_text = text
        self.config_file = str(path)
        self.loaded_config_file = str(path)
        self.config_dirty = False

    def save_config(self, path):
        if not isinstance(yaml.safe_load(self.config_text), dict):
            raise ValueError("LLTF configuration must be a YAML mapping.")
        Path(path).write_text(self.config_text)
        self.config_file = str(path)
        self.loaded_config_file = str(path)
        self.config_dirty = False
        self.status = f"Saved configuration to {path}."

    def build_command(self, config_file=None):
        output_dir = self.output_dir or str(Path(self.decay_file).parent)
        output_file = self.output_file or str(
            Path(output_dir) / (Path(self.decay_file).stem + "_fit.json")
        )
        command = [
            sys.executable,
            "-m",
            MODULE,
            "fit",
            self.decay_file,
            self.irf_file,
            "-sp",
            output_dir,
            "-o",
            output_file,
        ]
        config = config_file if config_file is not None else self.config_file
        if config:
            command.extend(["-c", config])
        if self.find_optimal:
            command.extend(["-f", "-m", str(self.max_lifetimes), "-pt", str(self.prob_threshold)])
        else:
            command.extend(["-n", str(self.n_lifetimes)])
        if self.verbose:
            command.append("-v")
        return command

    def start(self):
        if self.running:
            raise RuntimeError("An LLTF analysis is already running.")
        if not Path(self.decay_file).is_file() or not Path(self.irf_file).is_file():
            raise ValueError("Load existing decay and IRF files first.")
        if (
            self.config_file
            and self.config_file != self.loaded_config_file
            and not self.config_dirty
        ):
            self.load_config(self.config_file)
        if not isinstance(yaml.safe_load(self.config_text), dict):
            raise ValueError("LLTF configuration must be a YAML mapping.")
        self.output_dir = self.output_dir or str(Path(self.decay_file).parent)
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        self.output_file = str(Path(self.output_dir) / (Path(self.decay_file).stem + "_fit.json"))
        self._workspace = tempfile.TemporaryDirectory(prefix="chisurf-lltf-")
        config = Path(self._workspace.name) / "configuration.yml"
        config.write_text(self.config_text)
        self.output = []
        self._queue = queue.Queue()
        self.returncode = None
        self.result = None
        self.status = "LLTF analysis is running…"
        self.process = subprocess.Popen(
            self.build_command(str(config)),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, "PYTHONUNBUFFERED": "1", "MPLBACKEND": "Agg"},
        )
        process = self.process

        def read_output():
            try:
                for line in process.stdout:
                    self._queue.put(line.rstrip("\n"))
            finally:
                process.stdout.close()

        self._reader = threading.Thread(target=read_output, name="lltf-output", daemon=True)
        self._reader.start()
        return self.process

    def poll(self):
        while True:
            try:
                self.output.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if self.process is None or self.process.poll() is None:
            return False
        process, self.process = self.process, None
        self.returncode = process.returncode
        if self._reader is not None:
            self._reader.join(timeout=0.05)
            self._reader = None
            while not self._queue.empty():
                self.output.append(self._queue.get_nowait())
        if self.returncode == 0 and Path(self.output_file).is_file():
            self.load_result(self.output_file)
            self.status = "LLTF fit completed."
        else:
            self.status = f"LLTF analysis failed or was stopped (exit {self.returncode})."
        if self._workspace is not None:
            self._workspace.cleanup()
            self._workspace = None
        return True

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.poll()

    def clear_output(self):
        self.output.clear()

    def load_result(self, path):
        result = json.loads(Path(path).read_text())
        if not isinstance(result, dict):
            raise ValueError("LLTF result must be a JSON object.")
        self.result = result
        self.output_file = str(path)
        return result

    def plot_arrays(self):
        if self.result is None or "model" not in self.result:
            return None
        decay = np.genfromtxt(self.decay_file, delimiter=None, skip_header=0, usecols=[0, 1])
        irf = np.genfromtxt(self.irf_file, delimiter=None, skip_header=0, usecols=[0, 1])
        decay = decay[np.isfinite(decay).all(axis=1)]
        irf = irf[np.isfinite(irf).all(axis=1)]
        model = self.result["model"]
        time = np.asarray(model["time"])
        fit = np.asarray(model["decay"])
        limits = self.result["time_range"]
        first, last = int(limits["start_idx"]), int(limits["stop_idx"])
        observed = decay[first:last, 1]
        if len(observed) != len(fit):
            raise ValueError("LLTF result fit range does not match the measured decay.")
        maximum = max(float(np.max(irf[:, 1])), 1e-30)
        return {
            "time": decay[:, 0],
            "decay": decay[:, 1],
            "irf_time": irf[:, 0],
            "irf": irf[:, 1] * float(np.max(observed)) / maximum,
            "model_time": time,
            "fit": fit,
            "residuals": (observed - fit) / np.sqrt(np.maximum(observed, 1.0)),
            "range": (decay[first, 0], decay[last - 1, 0]),
        }

    def close(self):
        self.stop()

    def export_preferences(self):
        return {
            key: getattr(self, key)
            for key in (
                "decay_file",
                "irf_file",
                "config_file",
                "output_dir",
                "n_lifetimes",
                "find_optimal",
                "max_lifetimes",
                "prob_threshold",
                "verbose",
                "config_text",
            )
        }

    def restore_preferences(self, settings):
        for key in self.export_preferences():
            if key in settings:
                setattr(self, key, settings[key])
