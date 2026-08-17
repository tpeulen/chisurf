"""The engine imports no GUI toolkit and names no GPU binding.

This is the whole point of the work it guards, stated as two assertions.

chimol has to run in a browser, and it could not -- not because the browser
lacked anything, but because the desktop code had two properties. The renderer
called ``wgpu.*`` directly, and ``wgpu-py``'s browser backend is an explicit
stub, so there was nothing to point that code at. And the engine imported Qt:
not just the windows, but the colour tables, the file readers, the panel's
layout arithmetic, and -- worst -- two package ``__init__`` files that eagerly
imported a widget, which alone made ``import chimol.render.pack`` require a
window system.

Both are fixed, and both are the kind of thing that comes back one import at a
time. A module that says ``import wgpu`` cannot run where ``wgpu-py`` does not;
a module that says ``from qtpy import ...`` cannot run where there is no window
server. Finding those one at a time during a port is how a port stops being
finishable, so they are found here instead.

Neither assertion has an allow-list. If one is ever needed it should be a
*shrinking* list with a dated reason, not a place to add a module to.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import textwrap

import pytest

#: The shipped package: the relocated engine, installed from ``modules/chimol``
#: (``~/dev/chimol``) as top-level ``chimol``. Resolved through the import
#: system so the test follows the installation the host actually uses.
_CHIMOL = pathlib.Path(__import__("chimol").__file__).resolve().parent

#: The repository root, for the subprocess' working directory.
_ROOT = pathlib.Path(__file__).resolve().parents[4]

#: Where the engine is importable from in a subprocess: the sibling checkout
#: symlinked at ``modules/chimol``. The installed (editable) chimol also works;
#: this keeps the test independent of the install.
_ENGINE_ROOT = _ROOT / "modules" / "chimol"

#: The modules that make up the engine: everything needed to build a scene,
#: shade it, lay the panel out and decide what a click means. Deliberately not
#: "every module" -- ``renderer.view`` and ``renderer.wgpu_view`` *are* the Qt
#: host, and a host is allowed to need a toolkit.
ENGINE_MODULES = (
    "chimol",
    "chimol.core.colors",
    "chimol.core.settings.config",
    "chimol.commands",
    "chimol.ui.input.mouse_modes",
    "chimol.ui.menus.objects",
    "chimol.hosts.qt.menu_bar",
    "chimol.render.picking",
    "chimol.hosts.base",
    "chimol.cmtk.events",
    "chimol.cmtk.keys",
    "chimol.hosts.native.app",
    "chimol.io.structure",
    "chimol.render.backend",
    "chimol.viewport.canvas",
    "chimol.hosts.native.canvas",
    "chimol.ui.gui_state",
    "chimol.core.camera.state",
    "chimol.render.compute",
    "chimol.render.depth_cue",
    "chimol.render.gpu.api",
    "chimol.render.gpu.enums",
    "chimol.ui.gui",
    "chimol.render.lighting",
    "chimol.render.markers",
    "chimol.render.pack",
    # The viewer itself. It is a ``QWidget`` when there is a toolkit and a plain
    # object when there is not (`chimol.hosts.toolkit`), which is what lets a page
    # run *the* viewer and *the* command layer rather than a second set of both.
    "chimol.core.viewer",
    "chimol.render.scene",
    "chimol.cmtk.widgets.command_line",
    "chimol.cmtk.painter",
    "chimol.cmtk.quad_painter",
    "chimol.render.wgpu_backend",
)

#: The host layer: the modules that are *allowed* to import Qt at module scope.
#:
#: A **shrinking** list, and the worklist for what is left of the port. Nine
#: modules, seven of them ``hosts/qt/`` panels that draw with Qt widgets what the
#: in-viewport panel already draws with quads -- so most of this list is closed
#: by moving those panels into the chrome, not by editing them. The two renderer
#: entries are the Qt widget and what is left of the image-composited overlay;
#: the scene builder (``core/viewer.py``) left the list when the viewer stopped
#: needing a toolkit to exist, and the whole *draw path* left it when
#: ``viewport/canvas.py`` was extracted -- ``wgpu_view`` is now Qt's event
#: translation and nothing else.
#:
#: Five left in the change that made the Qt-free window the default:
#: ``hosts/qt/hierarchy_panel.py`` (deleted), ``hosts/qt/timeline_panel.py`` (deleted --
#: nothing in the tree referred to it), ``plugins/density/model.py`` (already
#: toolkit-free), ``hosts/qt/menu_bar.py`` (the bar's *tables* are plain data; only
#: installing a ``QMenuBar`` needs Qt) and ``hosts/qt/picking.py`` (a projection and
#: an ``argmin``; it imported Qt for one ``isinstance`` against ``QRect``).
#:
#: "Imports Qt at module scope" means an *unconditional* import. A guarded
#: ``try: from qtpy import ... except ImportError:`` with a stand-in behind it
#: is the sanctioned shape -- that is what `chimol.hosts.toolkit` is -- and the
#: subprocess test above is what proves such a module really does load without
#: a toolkit.
#:
#: Never add to it. ``test_the_host_list_is_not_padded`` fails on an entry that
#: no longer needs to be here, which is how it shrinks.
HOSTS = frozenset({
    "hosts/qt/controls_panel.py",
    "hosts/qt/demos.py",
    "hosts/qt/window.py",
    "hosts/qt/rmf_panel.py",
    "hosts/qt/settings_table.py",
    "hosts/qt/overlay.py",
    "hosts/qt/wgpu_view.py",
})

#: ``import wgpu`` or ``from wgpu[.x] import ...``.
#:
#: Not bare ``wgpu.`` attribute access: the seam is imported as
#: ``from .gpu import api as wgpu`` precisely so call sites keep the binding's
#: spelling. The *import* is what ties a module to one implementation.
_IMPORTS_WGPU = re.compile(r"^\s*(?:import\s+wgpu\b|from\s+wgpu[\s.])", re.M)


def test_the_engine_imports_without_a_gui_toolkit():
    """Every engine module loads in a process where Qt cannot be imported.

    Run in a subprocess with a meta-path finder that refuses every binding. The
    finder implements ``find_spec``, and the test asserts the blocker actually
    blocks before trusting a single result -- the first version of this guard
    used ``find_module``/``load_module``, **removed in Python 3.12**, so it was
    silently skipped and every module "passed" with Qt fully available.
    """
    script = textwrap.dedent(
        f"""
        import sys

        _BLOCKED = {{"qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6"}}


        class _BlockQt:
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split(".")[0] in _BLOCKED:
                    raise ImportError("Qt is blocked: " + fullname)
                return None


        sys.meta_path.insert(0, _BlockQt())

        try:
            import qtpy
        except ImportError:
            pass
        else:
            raise SystemExit("the Qt blocker is a no-op; this guard proves nothing")

        import importlib

        failed = []
        for name in {ENGINE_MODULES!r}:
            try:
                importlib.import_module(name)
            except Exception as exc:
                failed.append(f"{{name}}: {{type(exc).__name__}}: {{exc}}")
        if failed:
            raise SystemExit("\\n".join(failed))
        print("ok")
        """
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_ENGINE_ROOT), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, cwd=str(_ROOT), env=env,
    )
    assert result.returncode == 0, (
        "these engine modules need a GUI toolkit to import:\n"
        + (result.stdout + result.stderr)[-3000:]
    )


#: The Qt-blocking preamble, shared by every subprocess below.
#:
#: It asserts the blocker *blocks* before anything else runs. The first version
#: of this guard used ``find_module``/``load_module``, **removed in Python
#: 3.12**, so it was silently skipped and every module "passed" with Qt fully
#: available -- which is the failure mode a portability guard cannot afford,
#: because it reports success either way.
_BLOCK_QT = """
import sys

_BLOCKED = {"qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6"}


class _BlockQt:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in _BLOCKED:
            raise ImportError("Qt is blocked: " + fullname)
        return None


sys.meta_path.insert(0, _BlockQt())

try:
    import qtpy
except ImportError:
    pass
else:
    raise SystemExit("the Qt blocker is a no-op; this guard proves nothing")
"""


def _run_without_qt(script: str) -> subprocess.CompletedProcess:
    """Run *script* in a subprocess where Qt cannot be imported.

    Parameters
    ----------
    script : str
        Python source, appended to :data:`_BLOCK_QT`.

    Returns
    -------
    subprocess.CompletedProcess
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_ENGINE_ROOT), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    # The offscreen canvas, forced: `rendercanvas.auto`'s last resort is to
    # `import PyQt5` and pick its Qt backend if that succeeds, so "automatic"
    # means Qt on any machine that has it. chimol never asks `auto` for exactly
    # that reason; this pins the backend so the test does not depend on whether
    # a windowing library happens to be installed.
    env["CHIMOL_CANVAS"] = "offscreen"
    return subprocess.run(
        [sys.executable, "-c", _BLOCK_QT + textwrap.dedent(script)],
        capture_output=True, text=True, cwd=str(_ROOT), env=env,
    )


def test_the_default_entry_path_runs_without_a_gui_toolkit():
    """``chimol``'s default run mode builds a viewer and renders a frame.

    Importing the modules is not the claim; *running* them is. This drives
    :class:`chimol.hosts.native.app.ChimolApp` end to end in a process where Qt raises
    on import -- the viewer, the command layer, the in-viewport panel and one
    real frame through the WGSL renderer -- because every previous version of
    "chimol without Qt" imported cleanly and then reached for a toolkit at the
    first click, the first menu or the first frame.

    Skipped where there is no WebGPU adapter, which is the one thing a build
    machine can legitimately lack.
    """
    result = _run_without_qt(
        """
        from chimol.hosts.native.canvas import is_available

        if not is_available():
            print("SKIP: no WebGPU adapter")
            raise SystemExit(0)

        from chimol.hosts.native.app import ChimolApp
        from chimol.hosts.web.page import demo_pdb_path

        app = ChimolApp(size=(640, 480))
        # T4 lysozyme, the structure this project uses for every protein
        # rendering check, and through the same command a user would type.
        app.cmd.do("load " + demo_pdb_path())
        app.cmd.do("as cartoon")

        image = app.draw_frame()
        assert image is not None, "the offscreen canvas rendered nothing"
        assert image.shape[:2] == (480, 640), image.shape
        # A frame with something in it. An all-black image is what a viewer
        # that built a scene and drew none of it returns, and it is the exact
        # failure a "did it run?" test otherwise passes.
        assert float(image[..., :3].mean()) > 1.0, "the frame is empty"

        # The panel is chrome the engine builds as quads; a frame without it is
        # a viewer with no way to load anything into it.
        quads = app.renderer._chrome_quads()
        assert quads is not None and len(quads), "no chrome in the frame"

        assert app.viewer.list_objects(), "the command layer loaded nothing"

        # A click, all the way through: the press/release pair is what the
        # window's own pointer handlers call, and picking used to be gated on
        # there being a QWidget.
        from chimol.cmtk.events import LEFT_BUTTON

        app.renderer.click(320.0, 240.0, LEFT_BUTTON)

        assert "qtpy" not in sys.modules, "something imported Qt after all"
        app.close()
        print("ok")
        """
    )
    assert result.returncode == 0, (
        "the default entry path needs a GUI toolkit:\n"
        + (result.stdout + result.stderr)[-4000:]
    )
    if "SKIP" in result.stdout:
        pytest.skip(result.stdout.strip())
    assert "ok" in result.stdout


def test_the_real_module_entry_point_runs_without_a_gui_toolkit():
    """``python -m chisurf.plugins.chimol`` opens chimol with no toolkit.

    The **real** dotted path, through ``runpy``, and that is the whole point of
    this test rather than the one above it. ``python -m <package>`` executes the
    package's ``__init__`` before its ``__main__``, so a single eager
    ``from ...app import MolViewPluginWindow`` at plugin-root scope imports Qt
    before the Qt-free entry point is ever reached -- which is exactly what
    happened, and which importing bare ``chimol.*`` off ``PYTHONPATH`` cannot
    see, because that never runs the plugin-root ``__init__`` at all.

    ``--check`` builds the viewer, the command layer and the panel, renders one
    frame and exits, so what is asserted is a run and not an import.
    """
    result = _run_without_qt(
        """
        import runpy

        sys.argv = ["chimol", "--check", "--size", "320x240"]
        try:
            runpy.run_module("chisurf.plugins.chimol", run_name="__main__")
        except SystemExit as exc:
            code = int(exc.code or 0)
        else:
            code = 0
        assert code == 0, f"the entry point exited {code}"
        assert "qtpy" not in sys.modules, "the default entry point imported Qt"
        print("ok")
        """
    )
    assert result.returncode == 0, (
        "`python -m chisurf.plugins.chimol` needs a GUI toolkit:\n"
        + (result.stdout + result.stderr)[-4000:]
    )
    assert "ok" in result.stdout


def test_qt_is_opt_in_at_the_entry_point():
    """``--qt`` is the only thing that reaches the Qt window.

    A source-level check, deliberately: the Qt branch cannot be *run* in the
    subprocess that proves the other one is toolkit-free, and what has to hold
    is a property of the dispatch rather than of a run -- that the default
    branch names the Qt-free host and Qt is behind a flag.
    """
    source = (_CHIMOL / "__main__.py").read_text(encoding="utf-8")
    assert "from .hosts.native.app import main" in source, (
        "the default branch no longer reaches the Qt-free host"
    )
    assert '"--qt" in args' in source, "Qt is no longer opt-in"


def test_only_the_native_backend_imports_the_gpu_binding():
    """No module outside ``render/gpu/native.py`` may import ``wgpu``."""
    backend = _CHIMOL / "render" / "gpu" / "native.py"
    offenders = []
    for path in sorted(_CHIMOL.rglob("*.py")):
        if path == backend or "__pycache__" in path.parts:
            continue
        code = "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        if _IMPORTS_WGPU.search(code):
            offenders.append(str(path.relative_to(_CHIMOL)))
    assert not offenders, (
        "these modules reach the GPU binding directly instead of through "
        "chimol.render.gpu.api: " + ", ".join(offenders)
    )


def test_the_engine_does_not_import_qt_at_module_scope():
    """A source-level cross-check on the import guard above.

    The subprocess test is the real one -- it catches transitive imports, which
    reading source cannot. This catches the opposite case: a module that grows a
    module-scope Qt import but is not in :data:`ENGINE_MODULES`, so the
    subprocess never loads it and the graph quietly re-poisons itself.
    """
    pattern = re.compile(r"^(?:from\s+(?:qtpy|PyQt5|PySide6)\b|import\s+qtpy\b)", re.M)
    offenders = []
    for path in sorted(_CHIMOL.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = str(path.relative_to(_CHIMOL))
        if relative in HOSTS:
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(relative)
    assert not offenders, (
        "these modules import Qt at module scope; move it inside the one "
        "function that needs it, or into `chimol.hosts`: " + ", ".join(offenders)
    )


def test_the_host_list_is_not_padded():
    """Every exemption is a module that really does import Qt.

    An allow-list that names modules which do not need exempting reads as more
    debt than there is, and hides the moment one of them becomes portable. This
    is what keeps :data:`HOSTS` a worklist rather than a habit.
    """
    pattern = re.compile(r"^(?:from\s+(?:qtpy|PyQt5|PySide6)\b|import\s+qtpy\b)", re.M)
    stale = [
        name
        for name in sorted(HOSTS)
        if not pattern.search((_CHIMOL / name).read_text(encoding="utf-8"))
    ]
    assert not stale, (
        "these no longer import Qt at module scope -- strike them from HOSTS: "
        + ", ".join(stale)
    )


def test_the_atom_dtype_matches_the_host():
    """chimol's atom row is the host's -- because the host takes it from chimol.

    The direction was inverted on 2026-08-14: ``chimol.io.atoms.ATOM_DTYPE``
    is the single definition, and ``chisurf.core.fio.structure.coordinates``
    re-exports it, the same inversion the trajectory DCD reader follows.
    Reading a PDB no longer pulls in the host application from the engine
    side -- the portability leak this test originally guarded against is gone
    by construction, and this assertion is the guard that keeps it that way:
    the two must stay the same object, not a drifted copy.
    """
    coordinates = pytest.importorskip(
        "chisurf.core.fio.structure.coordinates",
        reason="the host application is not importable here",
    )
    from chimol.io.atoms import ATOM_DTYPE

    assert ATOM_DTYPE is coordinates.atom_dtype
