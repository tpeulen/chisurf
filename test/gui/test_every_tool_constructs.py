"""Every plugin GUI tool must build, offscreen, without touching a server.

A tool whose ``__init__`` raises ships broken and nobody finds out until
somebody opens it -- a missing import, a ``None`` where a main window was
assumed, a dereference of something the GUI only has at runtime. Writing one
smoke test per tool by hand does not scale to 114 of them and rots as plugins
are added, so the list of tools is **discovered** from the manifests instead:
a new plugin is covered the moment it declares ``entrypoints.gui``.

Each tool is built in its **own subprocess**. That is not fastidiousness: a
tool that blocks on construction (see the ``BLOCKING`` list) would otherwise
wedge the whole test session, and a tool that segfaults would take the rest of
the suite with it. The cost is process startup per tool, which is why this is
marked ``slow`` and excluded from default runs; run it deliberately:

``QT_QPA_PLATFORM=offscreen pytest test/gui/test_every_tool_constructs.py -m slow``
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PLUGINS = _ROOT / "chisurf" / "plugins"

#: Manifests that describe a template or a scratch area rather than a plugin.
_SKIP_MARKERS = ("cookiecutter", "/_dev/")

#: Seconds a single tool gets to build before it counts as blocking.
_TIMEOUT = 90

#: Tools known to perform blocking work while constructing, with what they do.
#: A **shrinking** list: the entry is the defect, not permission for it. Each is
#: written up in ``okf/references/known-issues.md``.
BLOCKING = {
    # Fires four blocking RPCs while building -- mmfdb.status twice (its
    # Overview panel), mmfdb.users.list (the admin gate) and
    # mmfdb.security.auth.login -- so with no server up, opening the tool
    # freezes for 4 x the 5 s client timeout.
    "mmfdb_admin",
}

#: Tools that crash the interpreter while constructing. Also **shrinking**, and
#: also written up in ``okf/references/known-issues.md``. Both of these start
#: work on a background thread from ``__init__``, which is the side effect the
#: read-only-construction rule exists to forbid.
CRASHING = {
    # Schedules the vectorial PSF computation on a QThreadPool worker during
    # construction; the worker segfaults in PSFComputation.run.
    "psf_calculator",
    # Aborts, then segfaults, while building.
    "lightpath_simulator",
}

#: Every tool whose construction is known to be broken, for whatever reason.
KNOWN_BROKEN = BLOCKING | CRASHING

_SNIPPET = """
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
import importlib
from qtpy import QtWidgets

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
module, cls_name = {module!r}, {cls!r}
widget = getattr(importlib.import_module(module), cls_name)()
app.processEvents()
opened = getattr(widget, "_mmfdb_db", None)
assert opened is None, "opened a metadata-store connection while constructing"
print("CONSTRUCTED")
"""


def _gui_tools() -> list[tuple[str, str]]:
    """Return ``(plugin id, entrypoint)`` for every plugin with a GUI tool."""
    found: list[tuple[str, str]] = []
    for manifest in sorted(_PLUGINS.rglob("manifest.json")):
        if any(marker in manifest.as_posix() for marker in _SKIP_MARKERS):
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        entrypoint = (data.get("entrypoints") or {}).get("gui")
        if entrypoint and ":" in entrypoint:
            found.append((str(data.get("id") or manifest.parent.name), entrypoint))
    return found


TOOLS = _gui_tools()


def test_tools_were_discovered():
    """The discovery itself must not silently find nothing."""
    assert len(TOOLS) > 100, f"only {len(TOOLS)} GUI tools discovered"


def test_the_known_broken_lists_do_not_rot():
    """A listed name that is no longer a tool hides the next real one."""
    ids = {pid for pid, _ in TOOLS}
    stale = sorted(KNOWN_BROKEN - ids)
    assert not stale, f"BLOCKING/CRASHING name tools that no longer exist: {stale}"


@pytest.mark.slow
@pytest.mark.parametrize("plugin_id,entrypoint", TOOLS, ids=[pid for pid, _ in TOOLS])
def test_tool_constructs(plugin_id: str, entrypoint: str):
    """The tool builds offscreen, opening no metadata store on the way."""
    module, _, cls_name = entrypoint.partition(":")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        ["modules/mmfdb/src", "modules/imp-tricks/src", "."]
    )
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["MPLBACKEND"] = "Agg"
    code = _SNIPPET.format(module=module, cls=cls_name)
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            cwd=_ROOT,
            env=env,
        )
    except subprocess.TimeoutExpired:
        if plugin_id in KNOWN_BROKEN:
            pytest.xfail(f"{plugin_id} blocks while constructing (known)")
        pytest.fail(
            f"{plugin_id} did not finish constructing in {_TIMEOUT}s -- it is doing "
            "blocking work in __init__ (an RPC, a dialog, a nested event loop)"
        )
    if result.returncode != 0:
        if plugin_id in KNOWN_BROKEN:
            pytest.xfail(
                f"{plugin_id} fails while constructing, exit {result.returncode} (known)"
            )
        tail = "\n".join(result.stderr.strip().splitlines()[-12:])
        if not tail and "CONSTRUCTED" in result.stdout:
            # Built fine and then died on the way out. A teardown crash is a
            # real defect but a different one, and reporting it as "failed to
            # construct" with an empty traceback tells the reader nothing.
            pytest.xfail(
                f"{plugin_id} constructs, then exits with code {result.returncode} "
                "(crash during interpreter teardown)"
            )
        pytest.fail(
            f"{plugin_id} ({entrypoint}) failed to construct "
            f"(exit {result.returncode}):\n{tail or '<no stderr>'}"
        )
    assert "CONSTRUCTED" in result.stdout
    if plugin_id in KNOWN_BROKEN:
        pytest.fail(
            f"{plugin_id} constructs cleanly now -- remove it from BLOCKING/CRASHING "
            "and strike its entry in okf/references/known-issues.md"
        )
