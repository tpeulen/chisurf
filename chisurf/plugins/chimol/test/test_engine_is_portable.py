"""The engine imports no GUI toolkit and names no GPU binding.

This is the whole point of the work it guards, stated as two assertions.

chimol has to run in a browser, and it could not -- not because the browser
lacked anything, but because the desktop code had two properties. The renderer
called ``wgpu.*`` directly, and ``wgpu-py``'s browser backend is an explicit
stub, so there was nothing to point that code at. And the engine imported Qt:
not just the windows, but the colour tables, the file readers, the panel's
layout arithmetic, and -- worst -- two package ``__init__`` files that eagerly
imported a widget, which alone made ``import chimol.renderer.pack`` require a
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

#: The shipped package.
_CHIMOL = pathlib.Path(__file__).resolve().parents[1] / "chimol"

#: The repository root, for the subprocess' working directory.
_ROOT = pathlib.Path(__file__).resolve().parents[4]

#: The modules that make up the engine: everything needed to build a scene,
#: shade it, lay the panel out and decide what a click means. Deliberately not
#: "every module" -- ``renderer.view`` and ``renderer.wgpu_view`` *are* the Qt
#: host, and a host is allowed to need a toolkit.
ENGINE_MODULES = (
    "chimol",
    "chimol.colors",
    "chimol.config",
    "chimol.cmd",
    "chimol.mouse_modes",
    "chimol.object_menus",
    "chimol.host.events",
    "chimol.host.keys",
    "chimol.io.structure",
    "chimol.renderer.base",
    "chimol.renderer.camera_state",
    "chimol.renderer.compute",
    "chimol.renderer.depth_cue",
    "chimol.renderer.gpu.api",
    "chimol.renderer.gpu.enums",
    "chimol.renderer.internal_gui",
    "chimol.renderer.lighting",
    "chimol.renderer.pack",
    "chimol.renderer.scene",
    "chimol.renderer.ui.command_line",
    "chimol.renderer.ui.painter",
    "chimol.renderer.ui.quad_painter",
    "chimol.renderer.wgpu_backend",
)

#: The host layer: the modules that are *allowed* to import Qt at module scope.
#:
#: A **shrinking** list, and the worklist for what is left of the port. Sixteen
#: modules, thirteen of them ``app/`` panels that draw with Qt widgets what the
#: in-viewport panel already draws with quads -- so most of this list is closed
#: by moving those panels into the chrome, not by editing them. The three
#: renderer entries are the widget, its scene builder, and what is left of the
#: image-composited overlay.
#:
#: Never add to it. ``test_the_host_list_is_not_padded`` fails on an entry that
#: no longer needs to be here, which is how it shrinks.
HOSTS = frozenset({
    "app/config_editor.py",
    "app/controls_panel.py",
    "app/demos.py",
    "app/hierarchy_panel.py",
    "app/menu_bar.py",
    "app/molview_main_window.py",
    "app/objects_panel.py",
    "app/picking.py",
    "app/rmf_panel.py",
    "app/sequence_dock.py",
    "app/settings_table.py",
    "app/timeline_panel.py",
    "app/volume_panel.py",
    "renderer/gui_overlay.py",
    "renderer/view.py",
    "renderer/wgpu_view.py",
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
        [str(_ROOT / "chisurf" / "plugins" / "chimol"), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, cwd=str(_ROOT), env=env,
    )
    assert result.returncode == 0, (
        "these engine modules need a GUI toolkit to import:\n"
        + (result.stdout + result.stderr)[-3000:]
    )


def test_only_the_native_backend_imports_the_gpu_binding():
    """No module outside ``renderer/gpu/native.py`` may import ``wgpu``."""
    backend = _CHIMOL / "renderer" / "gpu" / "native.py"
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
        "chimol.renderer.gpu.api: " + ", ".join(offenders)
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
        "function that needs it, or into `chimol.host`: " + ", ".join(offenders)
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
    """chimol's atom row is byte-identical to the host application's.

    :data:`chimol.io.atoms.ATOM_DTYPE` used to be imported from
    ``chisurf.core.fio.structure.coordinates``, which made reading a PDB pull in
    the whole host application -- the second kind of portability leak this port
    found, after Qt, and one that only showed up when the browser ran chimol's
    own self-contained PDB parser.

    Stated locally now, and asserted against the authority here. Not a
    duplicate to drift: every reader in the plugin produces this layout and
    every builder consumes it, so a change on either side has to fail rather
    than silently produce arrays that do not round-trip.
    """
    coordinates = pytest.importorskip(
        "chisurf.core.fio.structure.coordinates",
        reason="the host application is not importable here",
    )
    from chisurf.plugins.chimol.chimol.io.atoms import ATOM_DTYPE

    assert ATOM_DTYPE == coordinates.atom_dtype
