"""Final Qt-host vs emtk-shell parity pass over every plugin GUI.

The Qt main window (``python -m chisurf --qt``) opens a plugin through
:func:`chisurf.core.plugin.registry.build_plugin_widget`: the plugin's emtk app inside an
``emtk.qt_host.ControlHost`` top-level window. The emtk shell (``python -m chisurf``) opens the
same app as a dock (:meth:`chisurf.emtk.main_app.EmtkShellApp.open_plugin`). Before the Qt
window is retired, every plugin is opened both ways, driven into the same realistic state (its
own demo data, its main action, every tab) and captured, so a reviewer can read the pairs.

Each host runs in its own subprocess with a fresh settings folder, so both start from the
shipped defaults. The emtk half runs first; its dock's content size is handed to the Qt half,
which sizes its window to match, so the pair differs only where hosting differs. The Qt window
is grabbed once more at the size it opens at by itself (``qt_natural``).

Command line::

    QT_QPA_PLATFORM=offscreen PYTHONPATH=... python -m test.gui.final_parity_plugins \\
        run [plugin ...] --out okf/plugins/emtk-ports/final-parity/plugins
    python -m test.gui.final_parity_plugins one <plugin> --host qt|emtk --out DIR [--size WxH]

Per plugin ``DIR/<plugin>/`` receives ``qt_<state>.png``, ``emtk_<state>.png`` (the dock),
``emtk_shell.png`` (the whole shell, for the dock's title and tint) and ``qt.json`` /
``emtk.json`` (steps taken, visible text per state, control inventory, hosting facts, errors).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
SHELL_SIZE = (1600, 1000)
#: A floated plugin window: 1200 x 800 of content under its title tab, like the Qt window.
FLOAT_BOX = (300.0, 90.0, 1200.0, 830.0)
MAX_PNG_WIDTH = 1000

#: Buttons that load a plugin's own example data, most specific first.
DEMO_RE = re.compile(
    r"^(load (an )?example|load example data|load demo|demo data|example data|"
    r"demo|example|load sample|sample data|simulate demo|make demo|generate demo|try (it|demo))\b",
    re.I,
)
#: A plugin's main action once data is in.
RUN_RE = re.compile(
    r"^(run|compute|calculate|fit|analy[sz]e|correlate|simulate|start|process|apply|go|"
    r"update|estimate|search|find|evaluate|generate|plot|refresh|histogram)\b",
    re.I,
)
#: Never pressed by the generic steps (hardware, accounts, network, files).
NEVER_RE = re.compile(
    r"(acquire|acquisition|laser|shutter|device|hardware|login|logout|sign|account|upload|"
    r"download|publish|install|update check|delete|remove|quit|exit|close|save|export)",
    re.I,
)

#: Per-plugin steps when the generic ones cannot reach a realistic state. A step is
#: ``("click", caption)``, ``("click_re", pattern)``, ``("wait", seconds)``, ``("capture", name)``,
#: ``("call", python)`` (``app`` is the plugin app), ``"demo"``, ``"run"``, ``"tabs"``.
GENERIC = ["capture:open", "demo", "open", "run", "capture:state", "tabs"]
#: A tool's open/add button, pressed when it has no demo of its own and a file is fed (FEEDS).
OPEN_RE = re.compile(
    r"^(add files?|add folder|open( a)?( file| files| folder| tttr| data)?|load( file| files| data)?|"
    r"files|folder|browse|choose( file)?|select file)\b",
    re.I,
)
_BH = "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
_TTTR = [_BH + "/m000.spc"]
_CLSM = ["test/data/clsm/Leica_SP5.ptu"]
_TRAJ = [
    "test/data/atomic_coordinates/trajectory/hgbp1/topol.pdb",
    "test/data/atomic_coordinates/trajectory/hgbp1/hgbp1_transition.dcd",
]
#: Real files a file dialog is fed for tools that ship no demo (a folder entry is copied whole).
FEEDS: dict[str, list[str]] = {
    **{
        pid: _TTTR
        for pid in (
            "photon_table",
            "tttr_header_edit",
            "tttr_lut_tools",
            "tttr_to_pto",
            "microtime_shifter",
            "tttr_splitter",
            "tttr_time_windows",
            "tttr_count_rate_analysis",
            "tttr_audifier",
            "ptu_alex_creator",
            "fcs_channel_preset",
        )
    },
    **{
        pid: _CLSM
        for pid in (
            "img_drift",
            "img_frc",
            "img_tracking",
            "img_pixel_intensity",
            "img_pixel_micro_time",
            "img_coloc",
            "img_pixel_nb",
            "imaging_tools",
            "spot_finder",
            "region_mle",
            "img_calibration",
            "psf_determination",
        )
    },
    **{
        pid: [_BH]
        for pid in (
            "burst_browser",
            "mfd_prepare",
            "bid_to_analysis",
            "batch_analysis",
            "burst_bva",
            "burst_2cde",
            "burst_background",
            "burst_irf_bg",
            "burst_gs",
        )
    },
    **{
        pid: ["test/data/tcspc/Jordi"]
        for pid in ("tr_anisotropy", "vv_vh_anisotropy", "vv_vh_g_factor")
    },
    **{
        pid: _TRAJ
        for pid in (
            "traj_align",
            "traj_convert",
            "traj_join",
            "traj_remove_clashes",
            "traj_rotate_translate",
            "traj_save_topology",
            "traj_fret",
            "traj_energy_calculator",
        )
    },
}
#: Worker time limit factors: hubs with many steps and tabs, long simulations.
SLOW = {
    "burst_analysis": 3.0,
    "burst_h2mm": 2.5,
    "burst_mle_analysis": 2.0,
    "img_flow": 2.0,
    "mmfdb_admin": 2.5,
    "fcs_correlator": 2.0,
    "chimol": 1.5,
    "lightpath_simulator": 2.0,
}
_TMP = "import tempfile; from pathlib import Path; tmp = Path(tempfile.mkdtemp());"
RECIPES: dict[str, list] = {
    # The demo registers a dataset and an Acquisition fit window (a main-window effect); this
    # app's own plots fill from a run of the default Simulation device, never real hardware.
    "acq": [
        "capture:open",
        ("call", "app.model.photon_limit = 128; app.model.start()", 90),
        "capture:state",
        "tabs",
    ],
    **{
        pid: [
            "capture:open",
            (
                "call",
                "app.model.topology_filename = %r; app.model.trajectory_filename = %r"
                % (str(REPO / _TRAJ[0]), str(REPO / _TRAJ[1])),
                60,
            ),
            (
                "click_re",
                r"^(Align|Convert|Join|Remove clashes|Rotate|Apply|Compute|Calculate|Run)",
                120,
            ),
            "capture:state",
            "tabs",
        ]
        for pid in (
            "traj_align",
            "traj_convert",
            "traj_join",
            "traj_remove_clashes",
            "traj_rotate_translate",
            "traj_save_topology",
            "traj_fret",
            "traj_energy_calculator",
        )
    },
    "accurate_fret": [
        "capture:open",
        (
            "call",
            _TMP
            + (
                "from chisurf.plugins.burst.accurate_fret.test.test_emtk_accurate_fret_parity import _bursts\n"
                "from chisurf.plugins.burst.accurate_fret.test.test_accurate_fret_plugin import TAU_D0\n"
                "c = app.controller\n"
                "while c.running:\n    c._future.result(); c.poll()\n"
                "app.model.n_bootstrap = 0; app.model.donor_lifetime = TAU_D0\n"
                "c.load(str(_bursts(tmp))); c._future.result(30); c.poll()"
            ),
            60,
        ),
        ("click", "Calibrate", 120),
        "capture:state",
        "tabs",
    ],
    # The VBEM fit runs on the backend; both hosts wait for it to finish, not for a quiet frame.
    "burst_ebfret": [
        "capture:open",
        "demo",
        ("click_re", r"^Run$", 10),
        (
            "call",
            "import time\nt0 = time.time()\n"
            "while app.gui.client.status().get('running') and time.time() - t0 < 300:\n"
            "    time.sleep(0.5)",
            30,
        ),
        "capture:state",
        "tabs",
    ],
    "burst_mle_analysis": [
        "capture:open",
        "demo",
        ("click_re", r"^Auto IRF", 120),
        ("click_re", r"^Fit bursts", 240),
        "capture:state",
        "tabs",
    ],
    "burst_h2mm": [
        "capture:open",
        (
            "call",
            _TMP
            + (
                "import shutil, copy\n"
                "from chisurf.plugins.burst.burst_h2mm.tests.test_emtk_h2mm_native import REPO_DATA, BURSTS, BH_SETUP\n"
                "shutil.copytree(REPO_DATA, tmp / 'data', ignore=shutil.ignore_patterns('.DS_Store'))\n"
                "app.editor.model.data = copy.deepcopy(BH_SETUP); app.model.set_setup(BH_SETUP)\n"
                "app.model.data_folder = str(tmp / 'data' / BURSTS)\n"
                "app.model.min_states = 2; app.model.max_states = 2; app.model.restarts = 1"
            ),
            30,
        ),
        ("click_re", r"^Run H2MM", 300),
        "capture:state",
        "tabs",
    ],
    "burst_analysis": [
        "capture:open",
        (
            "call",
            _TMP
            + (
                "import shutil\n"
                "from chisurf.plugins.burst.burst_selection.gui.model import save_setup\n"
                "from chisurf.plugins.burst.burst_analysis.tests.test_emtk_native_hub import DATA, SETUP\n"
                "[shutil.copy(DATA / n, tmp / n) for n in ('m000.spc', 'm001.spc')]\n"
                "save_setup('probe', SETUP); app.children['setup'].select_setup('probe')"
            ),
            20,
        ),
        ("click", "Next", 20),
        ("call", "app.children['data'].model.add_paths([tmp / 'm000.spc', tmp / 'm001.spc'])", 20),
        ("click", "Next", 20),
        ("click", "Next", 300),
        "capture:state",
        "tabs",
    ],
    "trace_browser": [
        "capture:open",
        "demo",
        ("wait", 30),
        ("call", "app.model.select_row(app.model.rows[0])", 60),
        "capture:state",
        "tabs",
    ],
    "intensity_trace": [
        "capture:open",
        "demo",
        "capture:state",
        ("call", "app.tab = 'HMM'", 10),
        ("click_re", r"^Compute HMM", 120),
        "capture:hmm",
        "tabs",
    ],
    "clsm": [
        "capture:open",
        (
            "call",
            "app.open_paths([%r])" % str(REPO / "test" / "data" / "clsm" / "Leica_SP5.ptu"),
            120,
        ),
        ("click_re", r"^Build CLSM", 120),
        ("click_re", r"^Add representation", 120),
        ("click_re", r"^Compute decay", 120),
        "capture:state",
        "tabs",
    ],
    "fcs_correlator": [
        "capture:open",
        ("call", "step = app.files_step; (step() if callable(step) else step).load_example()", 30),
        ("call", "app.select('correlator')", 10),
        (
            "call",
            "c = app.child; c.model.channel_a = '0'; c.model.channel_b = '1'; c.model.n_splits = 3",
            5,
        ),
        ("click", "Correlate", 180),
        "capture:state",
        "tabs",
    ],
    "pch": [
        "capture:open",
        "demo",
        ("click_re", r"^Compute PCH", 120),
        ("click_re", r"^Fit Model", 120),
        "capture:state",
        "tabs",
    ],
    # The shipped app logs in to a server (blocked here); the seeded in-process database of its own
    # tests stands in, with the records the retired Qt window's baseline was captured on.
    "mmfdb_admin": [
        "capture:open",
        (
            "call",
            _TMP
            + (
                "from chisurf.plugins.core.mmfdb_admin.test.seeded_admin import admin_client\n"
                "c = admin_client(); app.model.client = c; app.model._given_client = c; "
                "app.model.user = 'admin'; app.model.login_user = 'admin'; "
                "app.model.connection = 'connected'; app.model._apply_status(c.status())"
            ),
            30,
        ),
        "capture:state",
        ("scroll", 70, 300, 120),
        ("capture", "rail_bottom"),
        ("click_re", r"^Samples$", 30),
        ("capture", "samples"),
        ("click_re", r"Import ?/ ?Export$", 30),
        ("capture", "import_export"),
        ("click_re", r"^Spectra$", 30),
        ("capture", "spectra"),
        ("click_re", r"Provenance graph$", 30),
        ("capture", "provenance"),
        ("click_re", r"Processed products$", 30),
        ("capture", "products"),
        # Every rail panel once, for the inventory the retired Qt window's baseline is checked against.
        ("each", "app.model.panel_keys()", "app.model.select(key)"),
        "tabs",
    ],
    "lightpath_simulator": [
        "capture:open",
        ("call", "app.controller.auto_update = False; app.controller.reset()", 30),
        ("click_re", r"^Calculate Emission", 120),
        "capture:state",
        "tabs",
    ],
    "code_editor": [
        "capture:open",
        (
            "call",
            "app.model.open_file(%r)"
            % str(REPO / "chisurf" / "plugins" / "core" / "code_editor" / "__init__.py"),
            20,
        ),
        "capture:state",
        "tabs",
    ],
    "help": [
        "capture:open",
        ("call", "app.model.open_page('docs/concepts/accurate_fret.md')", 30),
        "capture:state",
        ("call", "app.model.update_search('burst')", 30),
        "capture:search",
        "tabs",
    ],
    "img_flow": [
        "capture:open",
        ("click_re", r"^Load example", 300),
        ("click_re", r"^Map flow", 300),
        "capture:state",
        "tabs",
    ],
    "img_pixel_phasor": [
        "capture:open",
        (
            "call",
            _TMP
            + (
                "from chisurf.plugins.microscopy.imaging_emtk.pixel_testing import flim_ptu\n"
                "p = tmp / 'flim.ptu'; flim_ptu(p, n_channels=1)\n"
                "app.model.frequency = 40.0; app.model.open_path(str(p))"
            ),
            60,
        ),
        ("click_re", r"^Run$", 120),
        "capture:state",
        "tabs",
    ],
    "hmm": [
        "capture:open",
        ("click", "Demo trace", 20),
        ("call", "app.model.n_states = 3", 5),
        ("click", "Fit", 120),
        "capture:state",
        "tabs",
    ],
    "tttr_image_browser": [
        "capture:open",
        "demo",
        ("wait", 60),
        ("call", "app.model.select_row(app.model.rows()[0])", 60),
        "capture:state",
        "tabs",
    ],
    "microtime_histogram": [
        "capture:open",
        ("click", "Generate synthetic demo", 60),
        ("click_re", r"^Compute", 60),
        "capture:state",
        "tabs",
    ],
}


def _png_downscale(path: Path) -> None:
    """Shrink *path* in place to at most :data:`MAX_PNG_WIDTH` pixels wide."""
    from PIL import Image

    with Image.open(path) as image:
        if image.width <= MAX_PNG_WIDTH:
            return
        height = round(image.height * MAX_PNG_WIDTH / image.width)
        image.convert("RGB").resize((MAX_PNG_WIDTH, height), Image.LANCZOS).save(path)


def _normal(text: str) -> str:
    from test.gui.emtk_port_parity import normalize

    return normalize(text)


def _inner(app):
    """The plugin app behind a shell child wrapper."""
    return app.__dict__.get("_control", app) if type(app).__name__ == "ClassicChild" else app


def _busy(app) -> bool:
    app = _inner(app) or app
    for owner in (app, getattr(app, "job", None), getattr(app, "model", None)):
        if owner is None:
            continue
        for name in ("running", "busy"):
            try:
                value = getattr(owner, name, False)
                if callable(value):
                    continue
                if value:
                    return True
            except Exception:  # noqa: BLE001 - a property that raises is not busy
                pass
    return False


class _Host:
    """What both halves offer the scenario: frames, visible text, clicks, captures."""

    name = ""

    def __init__(self, plugin_id: str, out: Path, result: dict) -> None:
        self.plugin_id = plugin_id
        self.out = out
        self.result = result
        from test.gui.emtk_port_parity import ControlRecorder

        self.recorder = ControlRecorder()
        #: Every control and string seen at a settled frame, over the whole scenario.
        self.union: set[str] = set()

    # -- the scenario's vocabulary -------------------------------------------------
    def texts(self) -> list[tuple[float, float, float, float, str]]:
        raise NotImplementedError

    def frame(self) -> None:
        raise NotImplementedError

    def click_at(self, x: float, y: float) -> None:
        raise NotImplementedError

    def scroll_at(self, x: float, y: float, amount: int) -> None:
        raise NotImplementedError

    def capture(self, name: str) -> None:
        raise NotImplementedError

    @property
    def app(self):
        raise NotImplementedError

    def settle(self, timeout: float = 30.0, quiet: float = 2.0) -> None:
        """Draw until the app is not busy and its visible text stops changing."""
        end = time.monotonic() + timeout
        last, stable_since = None, time.monotonic()
        while time.monotonic() < end:
            self.frame()
            now = tuple(t[4] for t in self.texts())
            if now != last:
                last, stable_since = now, time.monotonic()
            # A progress read-out ("0 %", "Computing…") is a job still running, whatever flags say.
            working = any(
                re.search(r"(\d\s?%|…$|\.\.\.$)", t) and re.search(r"(%|ing)", t) for t in now
            )
            if not _busy(self.app) and not working and time.monotonic() - stable_since >= quiet:
                self.union |= set(inventory(self))
                return
            time.sleep(0.05)
        self.result["notes"].append(f"settle timed out after {timeout:g}s")

    def find(self, caption: str | None = None, pattern: re.Pattern | None = None):
        for x, y, w, h, text in reversed(self.texts()):
            if w <= 0 or h <= 0:
                continue
            shown = text.strip()
            if caption is not None and shown == caption:
                return (x, y, w, h, text)
            if pattern is not None and pattern.search(_strip_icon(shown)):
                return (x, y, w, h, text)
        return None

    def click_text(self, caption=None, pattern=None) -> str | None:
        hit = self.find(caption, pattern)
        if hit is None:
            return None
        x, y, w, h, text = hit
        self.click_at(x + w / 2, y + h / 2)
        return text

    def controls(self) -> list[dict]:
        return list(self.recorder.rows)


def _strip_icon(text: str) -> str:
    i = 0
    while i < len(text) and (not text[i].isalnum()):
        i += 1
    return text[i:]


# --------------------------------------------------------------------------------------- #
# Qt half: the --qt main window's path, build_plugin_widget -> ControlHost
# --------------------------------------------------------------------------------------- #
class QtHalf(_Host):
    name = "qt"

    def __init__(self, plugin_id, out, result, size=None) -> None:
        super().__init__(plugin_id, out, result)
        from qtpy.QtWidgets import QApplication

        self.qapp = QApplication.instance() or QApplication([])
        self._texts: list = []
        self._install_text_tap()
        from chisurf.core.plugin.registry import (
            apply_manifest_statefulness,
            build_plugin_widget,
        )

        manifest = _manifest_object(plugin_id)
        t0 = time.monotonic()
        self.widget = build_plugin_widget(manifest)
        apply_manifest_statefulness(self.widget, manifest)
        result["open_seconds"] = round(time.monotonic() - t0, 2)
        hint = self.widget.window_size_hint() if hasattr(self.widget, "window_size_hint") else None
        natural = (self.widget.width(), self.widget.height())
        result["hosting"] = {
            "window_title": self.widget.windowTitle(),
            "window_icon_null": bool(self.widget.windowIcon().isNull()),
            "natural_size": list(natural),
            "size_hint": list(hint) if hint else None,
            "is_emtk_native_host": bool(getattr(self.widget, "is_emtk_native_host", False)),
            "focus_policy": int(self.widget.focusPolicy()),
            "control": type(self.widget.control).__name__,
        }
        self.widget.show()
        self.frame()
        self.frame()
        self.capture("natural")
        result["hosting"]["window_title_painted"] = self.widget.windowTitle()
        if size is not None:
            self.widget.resize(*size)
            self.frame()

    def _install_text_tap(self) -> None:
        from emtk.painter import ALIGN_HCENTER, ALIGN_RIGHT, ALIGN_VCENTER
        from emtk.qt_painter import QtPainter

        tap = self
        original_text = QtPainter.text
        original_push, original_pop = QtPainter.push_clip, QtPainter.pop_clip
        original_init = QtPainter.__init__

        def init(painter, *args, **kwargs):
            original_init(painter, *args, **kwargs)
            painter._tap_clips = []
            # Only the host's own paint (or its grab): a plot drawn into an offscreen image
            # through another QtPainter must not replace the window's strings.
            device = None
            with contextlib.suppress(Exception):
                device = args[0].device() if args else None
            widget = getattr(tap, "widget", None)
            painter._tap_mine = (
                device is None
                or widget is None
                or device is widget
                or type(device).__name__ == "QPixmap"
            )
            if painter._tap_mine:
                tap._texts = []

        def push(painter, x, y, w, h):
            clips = getattr(painter, "_tap_clips", [])
            if clips:
                cx, cy, cw, ch = clips[-1]
                l, t = max(x, cx), max(y, cy)
                r, b = min(x + w, cx + cw), min(y + h, cy + ch)
                clips.append((l, t, max(0.0, r - l), max(0.0, b - t)))
            else:
                clips.append((x, y, w, h))
            return original_push(painter, x, y, w, h)

        def pop(painter):
            clips = getattr(painter, "_tap_clips", [])
            if clips:
                clips.pop()
            return original_pop(painter)

        def text(painter, x, y, w, h, align, string, colour, bold=False):
            try:
                if not getattr(painter, "_tap_mine", True):
                    raise LookupError
                span = painter.text_width(string.split("\n")[0])
                line = painter.line_height()
                left = (
                    x + w - span
                    if align & ALIGN_RIGHT
                    else x + (w - span) / 2
                    if align & ALIGN_HCENTER
                    else x
                )
                top = y + (h - line) / 2 if align & ALIGN_VCENTER else y
                box = [left, top, span, line]
                clips = getattr(painter, "_tap_clips", [])
                if clips:
                    cx, cy, cw, ch = clips[-1]
                    l, t = max(box[0], cx), max(box[1], cy)
                    r, b = min(box[0] + box[2], cx + cw), min(box[1] + box[3], cy + ch)
                    box = [l, t, max(0.0, r - l), max(0.0, b - t)]
                tap._texts.append((*box, string))
            except Exception:  # noqa: BLE001 - recording must never break painting
                pass
            return original_text(painter, x, y, w, h, align, string, colour, bold)

        QtPainter.__init__ = init
        QtPainter.text = text
        QtPainter.push_clip = push
        QtPainter.pop_clip = pop

    @property
    def app(self):
        return self.widget.control

    def frame(self) -> None:
        self.qapp.processEvents()
        with self.recorder.installed():
            self.recorder.rows.clear()
            self.widget.repaint()
        self.qapp.processEvents()

    def texts(self):
        return list(self._texts)

    def click_at(self, x, y) -> None:
        from qtpy.QtCore import QPoint, Qt
        from qtpy.QtTest import QTest

        point = QPoint(int(round(x)), int(round(y)))
        QTest.mouseMove(self.widget, point)
        self.frame()
        QTest.mousePress(self.widget, Qt.LeftButton, Qt.NoModifier, point)
        self.frame()
        QTest.mouseRelease(self.widget, Qt.LeftButton, Qt.NoModifier, point)
        self.frame()

    def scroll_at(self, x, y, amount) -> None:
        from qtpy.QtCore import QPoint, Qt
        from qtpy.QtGui import QWheelEvent
        from qtpy.QtWidgets import QApplication

        point = QPoint(int(x), int(y))
        event = QWheelEvent(
            point,
            self.widget.mapToGlobal(point),
            QPoint(0, 0),
            QPoint(0, amount),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.ScrollUpdate,
            False,
        )
        QApplication.sendEvent(self.widget, event)
        self.frame()

    def capture(self, name: str) -> None:
        path = self.out / f"qt_{name}.png"
        self.frame()
        self.widget.grab().save(str(path))
        _png_downscale(path)
        self.result["captures"][name] = {
            "png": path.name,
            "size": [self.widget.width(), self.widget.height()],
            "texts": sorted({_normal(t[4]) for t in self.texts() if t[2] > 0} - {""}),
            "raw": [t[4] for t in self.texts() if t[2] > 0],
        }

    def close(self) -> None:
        control = self.widget.control
        closed = []
        original = getattr(control, "close", None)
        if callable(original):

            def spy(*a, **k):
                closed.append(True)
                return original(*a, **k)

            with contextlib.suppress(Exception):
                control.close = spy
        accepted = self.widget.close()
        self.qapp.processEvents()
        self.result["hosting"]["close_accepted"] = bool(accepted)
        # The host's own flag is set either way; only a call into the app's close() counts.
        self.result["hosting"]["control_closed"] = bool(closed)

    def key_probe(self) -> None:
        """Type into the host: keys must reach the control without an exception."""
        from qtpy.QtCore import Qt
        from qtpy.QtTest import QTest

        self.widget.setFocus()
        QTest.keyClick(self.widget, Qt.Key_Tab)
        self.frame()
        self.result["hosting"]["has_focus_after_click"] = bool(self.widget.hasFocus())


def _manifest_object(plugin_id: str):
    from chisurf.core.plugin.manifest import load_manifest

    for path in (REPO / "chisurf" / "plugins").rglob("manifest.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if data.get("id") == plugin_id:
            return load_manifest(path)
    raise KeyError(plugin_id)


# --------------------------------------------------------------------------------------- #
# emtk half: the shell, plugin as a dock
# --------------------------------------------------------------------------------------- #
class EmtkHalf(_Host):
    name = "emtk"

    def __init__(self, plugin_id, out, result) -> None:
        super().__init__(plugin_id, out, result)
        from emtk.testing import Driver

        from chisurf.emtk.main_app import EmtkShellApp
        from chisurf.emtk.plugins import manifests

        catalog = manifests()
        # A tool reached only through a hub (``menu_hidden``) still opens as a dock of its own.
        result["menu_hidden"] = bool(catalog[plugin_id].get("menu_hidden"))
        catalog[plugin_id]["menu_hidden"] = False
        self.shell = EmtkShellApp(catalog, console_history=False, console_session_file=False)
        # Which of a frame's strings the plugin drew (not the shell panels under a floated window).
        self._span = None
        original_draw_child = self.shell.draw_child

        def draw_child(painter, app, *args, **kwargs):
            mine = self.hosted is not None and app is self.hosted.app
            start = len(getattr(painter, "texts", ()))
            try:
                if not mine:
                    return original_draw_child(painter, app, *args, **kwargs)
                self.recorder.rows.clear()
                with self.recorder.installed():
                    return original_draw_child(painter, app, *args, **kwargs)
            finally:
                if mine:
                    self._span = (start, len(getattr(painter, "texts", ())))

        self.shell.draw_child = draw_child
        self.hosted = None
        self.driver = Driver(self.shell, size=SHELL_SIZE)
        self.driver.frame(2)
        t0 = time.monotonic()
        self.hosted = self.shell.open_plugin(plugin_id)
        end = time.monotonic() + 120
        while self.hosted.build is not None and time.monotonic() < end:
            self.driver.frame(1)
            time.sleep(0.02)
        self.frame()
        self.frame()
        result["open_seconds"] = round(time.monotonic() - t0, 2)
        window = self.shell.docks.window(self.hosted.key)
        box = self.hosted.box
        result["hosting"] = {
            "dock_title": str(getattr(window, "title", "")),
            "dock_tooltip": str(getattr(window, "tooltip", "") or ""),
            "dock_region": self.shell.docks.region_of(self.hosted.key),
            "dock_box": [round(v) for v in box] if box else None,
            "build_error": self.hosted.error,
            "control": type(_inner(self.hosted.app)).__name__ if self.hosted.app else None,
        }
        # The dock where the shell puts it first (hosting evidence), then floated to the size
        # the Qt window opens at, so the scenario's pair compares like with like.
        self.settle(timeout=20)
        self.capture("docked")
        self.shell.docks.undock(self.hosted.key, FLOAT_BOX)
        self.frame()
        self.frame()
        box = self.hosted.box
        result["hosting"]["float_box"] = [round(v) for v in box] if box else None

    @property
    def app(self):
        return self.hosted.app

    def frame(self) -> None:
        self._span = None
        self.driver.frame(1)

    def texts(self):
        box = self.hosted.box
        painter = self.driver.painter
        rows = getattr(painter, "visible_texts", None) or painter.texts
        if self._span is not None:
            rows = rows[self._span[0] : self._span[1]]
        out = []
        for entry in rows:
            x, y, w, h, string = entry[0], entry[1], entry[2], entry[3], entry[5]
            if box and not (
                box[0] <= x + w / 2 <= box[0] + box[2] and box[1] <= y + h / 2 <= box[1] + box[3]
            ):
                continue
            out.append((x, y, w, h, string))
        return out

    def click_at(self, x, y) -> None:
        self.driver.click((x, y))

    def scroll_at(self, x, y, amount) -> None:
        self.driver.wheel(amount, at=(x, y))

    def capture(self, name: str) -> None:
        from PIL import Image

        full = self.out / "_shell_tmp.png"
        self.frame()
        self.driver.screenshot(full)
        box = self.hosted.box or (0, 0, *SHELL_SIZE)
        tab = 30  # the dock's title tab above its content box
        x, y, w, h = (int(round(v)) for v in box)
        path = self.out / f"emtk_{name}.png"
        with Image.open(full) as image:
            image.crop((max(0, x), max(0, y - tab), x + w, y + h)).save(path)
            if name in ("docked", "state") or not (self.out / "emtk_shell.png").exists():
                image.convert("RGB").save(self.out / "emtk_shell.png")
        full.unlink(missing_ok=True)
        _png_downscale(path)
        _png_downscale(self.out / "emtk_shell.png")
        self.result["captures"][name] = {
            "png": path.name,
            "size": [w, h],
            "texts": sorted({_normal(t[4]) for t in self.texts() if t[2] > 0} - {""}),
            "raw": [t[4] for t in self.texts() if t[2] > 0],
        }

    def close(self) -> None:
        app = _inner(self.hosted.app)
        closed = []
        original = getattr(app, "close", None) if app is not None else None
        if callable(original):

            def spy(*a, **k):
                closed.append(True)
                return original(*a, **k)

            with contextlib.suppress(Exception):
                app.close = spy
        self.shell.close_plugin(self.plugin_id)
        self.driver.frame(1)
        self.result["hosting"]["control_closed"] = bool(closed)
        self.result["hosting"]["dock_removed"] = self.shell.docks.window(self.hosted.key) is None

    def key_probe(self) -> None:
        pass


# --------------------------------------------------------------------------------------- #
# the scenario, identical for both halves
# --------------------------------------------------------------------------------------- #
def run_scenario(host: _Host, steps: list) -> None:
    result = host.result
    namespace = {"host": host, "REPO": REPO}
    host.settle(timeout=20)
    for step in steps:
        label = step if isinstance(step, str) else step[0]
        try:
            if isinstance(step, str) and step.startswith("capture:"):
                host.capture(step.split(":", 1)[1])
            elif step == "demo":
                pressed = None
                for row in host.controls():
                    shown = _strip_icon(row["label"]).strip()
                    if row["kind"] in (
                        "button",
                        "small_button",
                        "menu_item",
                        "selectable",
                    ) and DEMO_RE.search(shown):
                        pressed = host.click_text(caption=row["label"].strip()) or host.click_text(
                            pattern=re.compile(re.escape(shown) + "$")
                        )
                        if pressed:
                            break
                result["steps"].append({"demo": pressed})
                if pressed:
                    host.settle(timeout=60)
            elif step == "open":
                pressed = None
                demo_pressed = any(st.get("demo") for st in result["steps"] if "demo" in st)
                if result.get("demo_dir") and not demo_pressed:
                    for row in host.controls():
                        shown = _strip_icon(row["label"]).strip()
                        if (
                            row["kind"] in ("button", "small_button")
                            and OPEN_RE.search(shown)
                            and not NEVER_RE.search(shown)
                        ):
                            pressed = host.click_text(
                                caption=row["label"].strip()
                            ) or host.click_text(pattern=re.compile(re.escape(shown) + "$"))
                            if pressed:
                                break
                result["steps"].append({"open": pressed})
                if pressed:
                    host.settle(timeout=90)
            elif step == "run":
                pressed = None
                for row in host.controls():
                    shown = _strip_icon(row["label"]).strip()
                    if (
                        row["kind"] in ("button", "small_button")
                        and RUN_RE.search(shown)
                        and not NEVER_RE.search(shown)
                    ):
                        pressed = host.click_text(caption=row["label"].strip()) or host.click_text(
                            pattern=re.compile(re.escape(shown) + "$")
                        )
                        if pressed:
                            break
                result["steps"].append({"run": pressed})
                if pressed:
                    host.settle(timeout=90)
            elif step == "tabs":
                seen = []
                for _round in range(12):
                    tabs = [
                        r["label"].strip()
                        for r in host.controls()
                        if r["kind"] == "begin_tab_item" and r["label"].strip()
                    ]
                    todo = [t for t in tabs if t not in seen]
                    if not todo:
                        break
                    tab = todo[0]
                    seen.append(tab)
                    if host.click_text(caption=tab) is None:
                        continue
                    host.settle(timeout=20)
                    host.capture(f"tab{len(seen)}")
                    result["captures"][f"tab{len(seen)}"]["tab"] = tab
                result["steps"].append({"tabs": seen})
                # The tabs of the app's own dock regions (a plot dock behind another one).
                from emtk.i18n import tr

                from test.e2e.test_click_all_plugins import dock_managers

                docked = []
                for manager in dock_managers(_inner(host.app)):
                    for region, keys in list(manager.tabs.items()):
                        active = manager.active_tab(region)
                        for key in list(keys):
                            window = manager.windows.get(key)
                            if key == active or window is None or len(docked) >= 10:
                                continue
                            title = tr(str(window.title)).strip()
                            if not title or host.click_text(caption=title) is None:
                                continue
                            docked.append(title)
                            host.settle(timeout=20)
                            name = f"dock{len(docked)}"
                            host.capture(name)
                            result["captures"][name]["tab"] = title
                result["steps"].append({"dock_tabs": docked})
            elif label == "click":
                result["steps"].append({"click": step[1], "hit": host.click_text(caption=step[1])})
                host.settle(timeout=step[2] if len(step) > 2 else 30)
            elif label == "click_re":
                result["steps"].append(
                    {"click_re": step[1], "hit": host.click_text(pattern=re.compile(step[1], re.I))}
                )
                host.settle(timeout=step[2] if len(step) > 2 else 30)
            elif label == "scroll":
                host.scroll_at(step[1], step[2], step[3])
                host.settle(timeout=2, quiet=0.5)
                result["steps"].append({"scroll": [step[1], step[2], step[3]]})
            elif label == "each":
                namespace["app"] = _inner(host.app)
                keys = list(eval(step[1], namespace))  # noqa: S307 - recipe text written in this module
                for key in keys:
                    namespace["key"] = key
                    exec(step[2], namespace)  # noqa: S102
                    host.settle(timeout=20, quiet=0.5)
                result["steps"].append({"each": len(keys)})
            elif label == "wait":
                host.settle(timeout=step[1])
            elif label == "capture":
                host.capture(step[1])
            elif label == "call":
                namespace["app"] = _inner(host.app)
                exec(step[1], namespace)  # noqa: S102 - recipe text written in this module
                host.settle(timeout=step[2] if len(step) > 2 else 60)
                result["steps"].append({"call": step[1]})
        except Exception as exc:  # noqa: BLE001 - a step that fails is a finding, not a crash
            result["errors"].append(f"step {step!r}: {type(exc).__name__}: {exc}")
            result["tracebacks"].append(traceback.format_exc()[-3000:])


def inventory(host: _Host) -> list[str]:
    labels = set()
    for row in host.controls():
        name = row["label"] or row["id"].lstrip("#")
        if name:
            labels.add(_normal(name))
    for t in host.texts():
        labels.add(_normal(t[4]))
    labels.discard("")
    return sorted(labels)


def run_one(plugin_id: str, which: str, out: Path, size=None) -> int:
    out.mkdir(parents=True, exist_ok=True)
    result = {
        "plugin": plugin_id,
        "host": which,
        "captures": {},
        "steps": [],
        "errors": [],
        "tracebacks": [],
        "notes": [],
        "dialogs_closed": 0,
        "blocked_actions": [],
    }
    json_path = out / f"{which}.json"
    json_path.write_text(json.dumps(dict(result, status="running"), indent=2))
    from test.e2e.test_click_all_plugins import _guards, provision_demo

    with (
        tempfile.TemporaryDirectory(prefix="final-parity-") as scratch,
        contextlib.ExitStack() as stack,
    ):
        demo = provision_demo(plugin_id, scratch, result)
        if demo:
            result["demo_dir"] = str(demo)
        elif plugin_id in FEEDS:
            import shutil

            fed = Path(scratch) / "fed"
            fed.mkdir()
            for source in FEEDS[plugin_id]:
                source = REPO / source
                if source.is_dir():
                    shutil.copytree(
                        source, fed / source.name, ignore=shutil.ignore_patterns(".DS_Store")
                    )
                else:
                    shutil.copy2(source, fed / source.name)
            # A folder dialog gets the data folder itself, a file dialog the first matching file.
            only = [p for p in fed.iterdir()]
            result["demo_dir"] = result["fed_dir"] = str(
                only[0] if len(only) == 1 and only[0].is_dir() else fed
            )
        result["stub_dir"] = str(Path(scratch) / "stubs")
        if plugin_id == "mmfdb_admin":
            from chisurf.plugins.core.mmfdb_admin.test import seeded_admin

            seeded_admin.use_folder(Path(scratch) / "mmfdb")
            seeded_admin.seed(Path(scratch) / "mmfdb", seeded_admin.admin_client())
        from qtpy.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        _guards(stack, result)
        from chisurf.emtk.i18n import install

        install()
        host = None
        try:
            host = (
                QtHalf(plugin_id, out, result, size)
                if which == "qt"
                else EmtkHalf(plugin_id, out, result)
            )
            run_scenario(host, RECIPES.get(plugin_id, GENERIC))
            result["inventory"] = sorted(host.union | set(inventory(host)))
            host.key_probe()
            host.close()
            result["status"] = "done"
        except Exception as exc:  # noqa: BLE001
            result["status"] = "failed"
            result["errors"].append(f"{type(exc).__name__}: {exc}")
            result["tracebacks"].append(traceback.format_exc()[-4000:])
    result.pop("stub_dir", None)
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


def _env(scratch: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("MMFDB_")}
    env.update(
        QT_QPA_PLATFORM="offscreen",
        MPLBACKEND="Agg",
        PYTHONUNBUFFERED="1",
        CHISURF_SETTINGS_DIR=str(scratch / "settings"),
        # No MMFDB_DATABASE_PATH: a configured-but-absent database makes the dye tools refuse to
        # open (both hosts alike); unset, they read the shipped reference, as a fresh install does.
        MMFDB_SETTINGS_DIR=str(scratch / "mmfdb"),
        XDG_CACHE_HOME=str(scratch / "cache"),
        LUMIS_QUEST_HOME=str(scratch / "lumis"),
    )
    paths = [
        str(REPO),
        str(REPO / "modules" / "chimol"),
        str(REPO / "modules" / "mmfdb" / "src"),
        str(REPO / "modules" / "chinet"),
        str(REPO / "modules" / "imp-tricks" / "src"),
    ]
    env["PYTHONPATH"] = os.pathsep.join(paths)
    return env


def run_many(ids: list[str], out: Path, timeout: float) -> None:
    for plugin_id in ids:
        target = out / plugin_id
        target.mkdir(parents=True, exist_ok=True)
        size = None
        for which in ("emtk", "qt"):
            with tempfile.TemporaryDirectory(prefix="final-parity-env-") as scratch:
                command = [
                    sys.executable,
                    "-m",
                    "test.gui.final_parity_plugins",
                    "one",
                    plugin_id,
                    "--host",
                    which,
                    "--out",
                    str(target),
                ]
                if which == "qt" and size:
                    command += ["--size", f"{size[0]}x{size[1]}"]
                t0 = time.monotonic()
                try:
                    done = subprocess.run(
                        command,
                        cwd=REPO,
                        env=_env(Path(scratch)),
                        capture_output=True,
                        text=True,
                        timeout=timeout * SLOW.get(plugin_id, 1.0),
                    )
                    log = done.stdout + done.stderr
                except subprocess.TimeoutExpired as exc:
                    log = f"TIMEOUT after {timeout}s\n{exc.stdout or ''}{exc.stderr or ''}"
                    data = _load(target / f"{which}.json")
                    data.update(status="timeout")
                    data.setdefault("errors", []).append(f"worker exceeded {timeout:g}s")
                    (target / f"{which}.json").write_text(json.dumps(data, indent=2, default=str))
                (target / f"{which}.log").write_text(
                    log[-20000:] if isinstance(log, str) else str(log)
                )
                data = _load(target / f"{which}.json")
                print(
                    f"{plugin_id:28s} {which:4s} {data.get('status')} {time.monotonic() - t0:5.1f}s "
                    f"captures={list(data.get('captures', {}))} errors={len(data.get('errors', []))}",
                    flush=True,
                )
                if which == "emtk":
                    box = (data.get("hosting") or {}).get("float_box")
                    if box:
                        size = (box[2], box[3])


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return {}


# --------------------------------------------------------------------------------------- #
# the report: measured facts per plugin, plus the reviewer's verdicts (verdicts.json)
# --------------------------------------------------------------------------------------- #
#: Where the Qt-era inventories of the tools retired before this pass live.
PORTS = REPO / "okf" / "plugins" / "emtk-ports"
#: Captures shown as pairs, in this order; ``tabN`` follow.
PAIR_ORDER = ("open", "state")


def _explained(plugin_id: str) -> set[str]:
    keys: set[str] = set()
    folder = PORTS / plugin_id
    for name in ("deliberate.json", "retire_deliberate.json"):
        data = _load(folder / name)
        keys |= {_normal(k) for k in data}
    keys |= {_normal(k) for k in (_load(folder / "retire_compare.json").get("explained") or {})}
    return keys


def retire_check(plugin_id: str, emtk: dict) -> dict | None:
    """Every control of the truly-Qt widget retired earlier must still be in the emtk app."""
    before = _load(PORTS / plugin_id / "retire_qt_before.json")
    if not before:
        return None
    wanted = {_normal(c) for c in before.get("controls", [])} - {""}
    have = set(emtk.get("inventory") or [])
    for capture in (emtk.get("captures") or {}).values():
        have |= set(capture.get("texts") or [])
    explained = _explained(plugin_id)
    missing = sorted(wanted - have)
    return {
        "baseline": f"../../{plugin_id}/retire_qt_before.json",
        "baseline_controls": len(wanted),
        "missing_unexplained": [c for c in missing if c not in explained],
        "missing_explained": [c for c in missing if c in explained],
    }


#: Strings that differ between two runs by construction: scratch paths, clocks, timings.
_NOISE = re.compile(r"(/|\\|final-par|parity-env|^\d+(\.\d+)?(ms|s)$|\d\d:\d\d)", re.I)


def _words(capture: dict) -> set[str]:
    """The words a capture shows: wrapping (Qt and emtk measure text differently) is not a difference."""
    raw = capture.get("raw")
    if raw is None:
        return set(capture.get("texts") or [])
    words = set()
    for string in raw:
        for word in str(string).split():
            word = word.strip(".,;:()[]{}'\"").lower()
            if word and not _NOISE.search(word):
                words.add(word)
    return words


def measure(out: Path) -> dict:
    """Per plugin: what each host did and saw, and where the two differ."""
    from chisurf.emtk.plugins import manifests

    catalog = manifests()
    plugins = {}
    for folder in sorted(p for p in out.iterdir() if p.is_dir() and (p / "emtk.json").exists()):
        pid = folder.name
        emtk, qt = _load(folder / "emtk.json"), _load(folder / "qt.json")
        shared = [k for k in emtk.get("captures", {}) if k in qt.get("captures", {})]
        shared.sort(key=lambda k: (PAIR_ORDER.index(k) if k in PAIR_ORDER else 9, k))
        pairs = []
        for key in shared:
            a, b = qt["captures"][key], emtk["captures"][key]
            ta, tb = _words(a), _words(b)
            pairs.append(
                {
                    "state": key,
                    "tab": b.get("tab") or a.get("tab"),
                    "qt": f"{pid}/{a['png']}",
                    "emtk": f"{pid}/{b['png']}",
                    "only_qt": sorted(ta - tb)[:40],
                    "only_emtk": sorted(tb - ta)[:40],
                    "texts_qt": len(ta),
                    "texts_emtk": len(tb),
                }
            )
        steps_qt, steps_emtk = qt.get("steps", []), emtk.get("steps", [])
        plugins[pid] = {
            "plugin": pid,
            "display_name": (catalog.get(pid) or {}).get("display_name", pid),
            "menu_hidden": emtk.get("menu_hidden", False),
            "status": {"qt": qt.get("status"), "emtk": emtk.get("status")},
            "errors": {"qt": qt.get("errors", []), "emtk": emtk.get("errors", [])},
            "notes": {"qt": qt.get("notes", []), "emtk": emtk.get("notes", [])},
            "steps": {"qt": steps_qt, "emtk": steps_emtk},
            "steps_differ": steps_qt != steps_emtk,
            "demo_fed": {"qt": qt.get("demo_fed", []), "emtk": emtk.get("demo_fed", [])},
            "open_seconds": {"qt": qt.get("open_seconds"), "emtk": emtk.get("open_seconds")},
            "hosting": {"qt": qt.get("hosting", {}), "emtk": emtk.get("hosting", {})},
            "natural": f"{pid}/qt_natural.png" if (folder / "qt_natural.png").exists() else None,
            "docked": f"{pid}/emtk_docked.png" if (folder / "emtk_docked.png").exists() else None,
            "pairs": pairs,
            "text_differences": sum(len(p["only_qt"]) + len(p["only_emtk"]) for p in pairs),
            "retire_baseline": retire_check(pid, emtk),
        }
    return plugins


def _html_escape(text) -> str:
    import html

    return html.escape(str(text), quote=True)


VERDICT_ORDER = ("blocker", "fixed", "defect", "deliberate", "parity")


def render(out: Path) -> None:
    """Write ``report.json``, ``README.md`` and ``index.html`` from the captures and verdicts."""
    measured = measure(out)
    verdicts = _load(out / "verdicts.json")
    for pid, entry in measured.items():
        verdict = verdicts.get(pid) or {}
        entry["verdict"] = verdict.get("verdict", "unreviewed")
        entry["review"] = verdict.get("notes", [])
        entry["deliberate"] = verdict.get("deliberate", [])
        entry["commits"] = verdict.get("commits", [])
    report = {
        "generated": time.strftime("%Y-%m-%d"),
        "tool": "test/gui/final_parity_plugins.py",
        "method": (
            "Each plugin opened twice from a fresh settings folder: in the --qt main window's host "
            "(build_plugin_widget -> emtk.qt_host.ControlHost, offscreen grab) and as a dock of the emtk "
            "shell (EmtkShellApp.open_plugin, headless Driver screenshot; first where the shell docks it, "
            "then floated to the Qt window's 1200 x 800). The same scenario drives both: the plugin's own "
            "demo (provisioned like the click-all harness, file dialogs fed the demo), its main action, "
            "every tab. Visible text per state is compared; the pairs were read by the reviewer."
        ),
        "plugins": measured,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    counts: dict[str, int] = {}
    for entry in measured.values():
        counts[entry["verdict"]] = counts.get(entry["verdict"], 0) + 1
    lines = [
        "# Final Qt-vs-emtk parity pass — plugins",
        "",
        f"Generated {report['generated']} by `{report['tool']}`. {report['method']}",
        "",
        "Open [index.html](index.html) for the side-by-side pairs. Verdicts: "
        + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())),
        "",
        "| Plugin | Verdict | Pairs | Text diffs | Qt-era baseline | Notes |",
        "|---|---|---|---|---|---|",
    ]
    for pid, e in sorted(measured.items(), key=lambda kv: (_rank(kv[1]["verdict"]), kv[0])):
        base = e["retire_baseline"]
        base_cell = (
            "—"
            if base is None
            else (
                f"lost {len(base['missing_unexplained'])}"
                if base["missing_unexplained"]
                else "all present"
            )
        )
        note = "; ".join(e["review"])[:400].replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| `{pid}` | {e['verdict']} | {len(e['pairs'])} | {e['text_differences']} | {base_cell} | {note} |"
        )
    (out / "README.md").write_text(
        "---\n"
        "type: Report\n"
        "title: Final Qt-vs-emtk parity pass — plugins\n"
        "description: Capture evidence for all 120 plugin GUIs opened in both the --qt\n"
        "  ControlHost window and the emtk shell dock, driven into the same realistic state;\n"
        "  reviewer verdicts are recorded against these pairs before the Qt shell is retired.\n"
        "---\n\n" + "\n".join(lines) + "\n"
    )
    (out / "index.html").write_text(_index_html(report, counts))


def _rank(verdict: str) -> int:
    return VERDICT_ORDER.index(verdict) if verdict in VERDICT_ORDER else len(VERDICT_ORDER)


def _index_html(report: dict, counts: dict) -> str:
    esc = _html_escape
    cards = []
    entries = sorted(report["plugins"].values(), key=lambda e: (_rank(e["verdict"]), e["plugin"]))
    for e in entries:
        hq, he = e["hosting"]["qt"], e["hosting"]["emtk"]
        facts = [
            f"Qt window title: <code>{esc(hq.get('window_title_painted') or hq.get('window_title'))}</code>, "
            f"opens at {esc(hq.get('natural_size'))}, icon {'none' if hq.get('window_icon_null') else 'set'}, "
            f"close {'reaches the app' if hq.get('control_closed') else 'does NOT reach the app'}",
            f"emtk dock: <code>{esc(he.get('dock_title'))}</code> in region {esc(he.get('dock_region'))} "
            f"at {esc(he.get('dock_box'))}, close {'reaches the app' if he.get('control_closed') else 'does NOT reach the app'}"
            + (" (menu-hidden: reached through a hub)" if e.get("menu_hidden") else ""),
            f"steps Qt {esc(e['steps']['qt'])}; emtk {esc(e['steps']['emtk'])}",
        ]
        errors = e["errors"]["qt"] + e["errors"]["emtk"]
        if errors:
            facts.append("errors: " + esc("; ".join(errors)[:600]))
        base = e["retire_baseline"]
        if base is not None:
            facts.append(
                f'Qt-era baseline (<a href="{esc(base["baseline"])}">retire_qt_before.json</a>, '
                f"{base['baseline_controls']} controls): "
                + (
                    "<b>missing " + esc(", ".join(base["missing_unexplained"])) + "</b>"
                    if base["missing_unexplained"]
                    else "every control present"
                )
                + (
                    f"; explained elsewhere: {esc(', '.join(base['missing_explained']))}"
                    if base["missing_explained"]
                    else ""
                )
            )
        review = "".join(f"<li>{esc(n)}</li>" for n in e["review"])
        deliberate = "".join(f"<li>{esc(n)}</li>" for n in e["deliberate"])
        figs = []
        hosting_row = []
        if e.get("natural"):
            hosting_row.append(("Qt window as it opens", e["natural"]))
        if e.get("docked"):
            hosting_row.append(("emtk shell, docked where it opens", e["docked"]))
        if hosting_row:
            figs.append(
                '<div class="pair">'
                + "".join(
                    f'<figure><a href="{esc(src)}"><img loading="lazy" src="{esc(src)}" alt="{esc(cap)}"></a>'
                    f"<figcaption>{esc(cap)}</figcaption></figure>"
                    for cap, src in hosting_row
                )
                + "</div>"
            )
        for p in e["pairs"]:
            label = p["state"] + (f" — tab {p['tab']}" if p.get("tab") else "")
            diff = ""
            if p["only_qt"] or p["only_emtk"]:
                diff = (
                    f'<p class="diff">text only in Qt: {esc(", ".join(p["only_qt"][:12]) or "—")}; '
                    f"only in emtk: {esc(', '.join(p['only_emtk'][:12]) or '—')}</p>"
                )
            figs.append(
                f'<h4>{esc(label)}</h4><div class="pair">'
                f'<figure><a href="{esc(p["qt"])}"><img loading="lazy" src="{esc(p["qt"])}" alt="Qt {esc(label)}"></a>'
                f"<figcaption>Qt host ({p['texts_qt']} strings)</figcaption></figure>"
                f'<figure><a href="{esc(p["emtk"])}"><img loading="lazy" src="{esc(p["emtk"])}" alt="emtk {esc(label)}"></a>'
                f"<figcaption>emtk dock ({p['texts_emtk']} strings)</figcaption></figure></div>{diff}"
            )
        cards.append(
            f'<section class="card" id="{esc(e["plugin"])}" data-verdict="{esc(e["verdict"])}">'
            f'<h2><span class="badge v-{esc(e["verdict"])}">{esc(e["verdict"])}</span> {esc(e["plugin"])} '
            f"<small>{esc(e['display_name'])}</small></h2>"
            + (f'<ul class="review">{review}</ul>' if review else "")
            + (
                f'<p class="lbl">Deliberate differences</p><ul>{deliberate}</ul>'
                if deliberate
                else ""
            )
            + "<details><summary>Measured facts</summary><ul>"
            + "".join(f"<li>{f}</li>" for f in facts)
            + "</ul></details>"
            + "".join(figs)
            + "</section>"
        )
    toc = "".join(
        f'<a class="chip v-{esc(e["verdict"])}" href="#{esc(e["plugin"])}">{esc(e["plugin"])}</a>'
        for e in entries
    )
    filters = "".join(
        f'<button data-f="{esc(k)}">{esc(k)} ({v})</button>'
        for k, v in sorted(counts.items(), key=lambda kv: _rank(kv[0]))
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Plugin Parity Pass</title>
<style>
:root {{ --bg:#f6f6f4; --fg:#1d1d1f; --muted:#5f6368; --card:#ffffff; --line:#d9d9d6;
  --blocker:#b3261e; --fixed:#1a73e8; --defect:#b06000; --deliberate:#6b4fbb; --parity:#1e8e3e; --unreviewed:#80868b; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#16171a; --fg:#e8eaed; --muted:#9aa0a6;
  --card:#1f2125; --line:#33363b; --blocker:#f28b82; --fixed:#8ab4f8; --defect:#fdd663; --deliberate:#c58af9; --parity:#81c995; }} }}
:root[data-theme="dark"] {{ --bg:#16171a; --fg:#e8eaed; --muted:#9aa0a6; --card:#1f2125; --line:#33363b;
  --blocker:#f28b82; --fixed:#8ab4f8; --defect:#fdd663; --deliberate:#c58af9; --parity:#81c995; }}
body {{ background:var(--bg); color:var(--fg); font:14px/1.45 system-ui, sans-serif; margin:0; padding:16px; }}
main {{ max-width:1500px; margin:0 auto; }}
h1 {{ font-size:22px; margin:0 0 6px; }} p.lead {{ color:var(--muted); max-width:110ch; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px 16px; margin:14px 0; }}
.card h2 {{ font-size:17px; margin:2px 0 8px; }} .card h2 small {{ color:var(--muted); font-weight:400; }}
h4 {{ margin:12px 0 4px; font-size:13px; color:var(--muted); }}
.pair {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
@media (max-width:760px) {{ .pair {{ grid-template-columns:1fr; }} }}
figure {{ margin:0; }} img {{ width:100%; height:auto; border:1px solid var(--line); border-radius:4px; display:block; }}
figcaption {{ color:var(--muted); font-size:12px; }}
.badge, .chip {{ display:inline-block; border-radius:10px; padding:1px 8px; font-size:12px; color:var(--bg); background:var(--unreviewed); }}
.chip {{ margin:2px; text-decoration:none; }}
.v-blocker {{ background:var(--blocker); }} .v-fixed {{ background:var(--fixed); }} .v-defect {{ background:var(--defect); }}
.v-deliberate {{ background:var(--deliberate); }} .v-parity {{ background:var(--parity); }}
.diff {{ color:var(--muted); font-size:12px; overflow-wrap:anywhere; }} code {{ overflow-wrap:anywhere; }}
.lbl {{ font-weight:600; margin:6px 0 0; }} details {{ color:var(--muted); font-size:12.5px; overflow-wrap:anywhere; }}
.filters button {{ background:var(--card); color:var(--fg); border:1px solid var(--line); border-radius:6px; padding:3px 9px; margin:2px; cursor:pointer; }}
</style></head><body><main>
<h1>Plugin parity pass: Qt host vs emtk dock</h1>
<p class="lead">{esc(report["method"])} Generated {esc(report["generated"])}. Data: <a href="report.json">report.json</a>, summary: <a href="README.md">README.md</a>.</p>
<div class="filters"><button data-f="all">all ({len(entries)})</button>{filters}</div>
<nav>{toc}</nav>
{"".join(cards)}
</main>
<script>
document.querySelectorAll('.filters button').forEach(b => b.addEventListener('click', () => {{
  const f = b.dataset.f;
  document.querySelectorAll('.card').forEach(c => {{ c.style.display = (f === 'all' || c.dataset.verdict === f) ? '' : 'none'; }});
}}));
</script></body></html>
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("one")
    one.add_argument("plugin")
    one.add_argument("--host", choices=("qt", "emtk"), required=True)
    one.add_argument("--out", type=Path, required=True)
    one.add_argument("--size", default=None)
    many = sub.add_parser("run")
    many.add_argument("plugins", nargs="*")
    many.add_argument("--out", type=Path, required=True)
    many.add_argument("--timeout", type=float, default=300.0)
    rep = sub.add_parser("report")
    rep.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.cmd == "report":
        render(args.out)
        return 0
    if args.cmd == "one":
        size = tuple(int(v) for v in args.size.split("x")) if args.size else None
        return run_one(args.plugin, args.host, args.out, size)
    ids = args.plugins
    if not ids:
        from chisurf.emtk.plugins import manifests

        ids = sorted(
            i
            for i, m in manifests().items()
            if (m.get("entrypoints") or {}).get("emtk") and "cookiecutter" not in i
        )
    run_many(ids, args.out, args.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
