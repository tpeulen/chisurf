"""The desktop host and the page answer the same, and something checks.

``web_parity`` runs one report on both hosts -- every registered command, the
chrome's reachable controls, the menu tree, the host gestures -- and compares
them. It is the strongest statement of the rule the whole engine is built
around: one code path, three hosts, differing only in where pixels go and where
events come from.

Nothing referenced it. It was a tool somebody ran by hand, so its answer was
only as fresh as the last time somebody thought to look, and it had drifted to
**nine** commands "behaving differently" -- every one of them an interpreter
version, an object address, a log timestamp or a count of the process's own
memory blocks, none of which can match by construction. A report that is red
when nothing is wrong is a report nobody reads, and a genuine divergence
arriving in that list would have been indistinguishable from the noise.

So the noise is gone (``parity.normalise`` absorbs what cannot match,
``parity.SKIP`` names the two commands that describe their own process) and
what is left is asserted here.

Both halves run in a **child process**, and that is not incidental:

* the desktop half is the toolkit-free host, which is chosen once per process
  from ``CHIMOL_TOOLKIT`` -- setting it here would reach every other test in
  the session, and ``MolViewPluginWindow`` would then be handed a ``Viewer``
  that is no longer a ``QWidget``;
* the plugin registries are still one table per process with a refcount of
  live loads (``plugins.api.holds``), so a viewer built beside the other
  tests' viewers reports ``dbg(5)`` where a fresh page reports ``dbg(1)``.
  Run in a process of its own it reports one, like the page.

Both are the same lesson ``toolkit_free.probe`` records, and this reaches for
the tool's own command line rather than re-deriving it. Slow: it starts a page
and waits for Pyodide, which is a minute, in the suite that already pays for
one.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def comparison(tmp_path_factory):
    """Both halves, captured in a child process, compared here."""
    pytest.importorskip("playwright.sync_api")
    from chimol.testing import parity

    out = tmp_path_factory.mktemp("parity")
    env = dict(os.environ)
    # The toolkit-free host is the like-for-like comparison for a page, and it
    # is chosen at import; a child process is the only place that choice can be
    # made without reaching the rest of the session.
    env["CHIMOL_TOOLKIT"] = "none"
    env["QT_QPA_PLATFORM"] = "offscreen"
    # Run in the report's directory: the capture presses every reachable
    # control, and one of them records an orbit movie into the working
    # directory -- from the checkout, orbit.gif and its frames landed in the
    # repository root. The package root is put on the path explicitly, since a
    # relative entry would no longer point at it.
    root = pathlib.Path(__file__).resolve().parents[4]
    env["PYTHONPATH"] = os.pathsep.join(
        [str(root), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    finished = subprocess.run(
        [sys.executable, "-m", "chisurf.plugins.chimol.test.web_parity",
         "--out", str(out)],
        capture_output=True, text=True, env=env, timeout=1800, cwd=str(out),
    )
    desktop = out / "desktop.json"
    browser = out / "browser.json"
    if not (desktop.is_file() and browser.is_file()):
        pytest.fail(
            "the capture wrote no report\n"
            + finished.stdout[-3000:] + "\n" + finished.stderr[-3000:]
        )
    return parity.compare(
        json.loads(desktop.read_text()), json.loads(browser.read_text())
    )


def test_the_two_hosts_register_the_same_commands(comparison):
    """A command the page does not have is a feature the page does not have."""
    assert comparison["commands_missing"] == []
    assert comparison["commands_extra"] == []


def test_no_command_answers_differently(comparison):
    """The report is a *diff*: an empty one is the whole claim.

    A difference here is either a real divergence or a value that cannot match
    across two runtimes. The second kind belongs in `parity.normalise` or
    `parity.SKIP`, with the reason written down -- not left in the report to
    make everything after it unreadable.
    """
    differing = comparison["probe_differences"]
    assert differing == [], "\n".join(
        f"{one['name']}\n  desktop: {one['desktop'][:200]}\n  browser: {one['browser'][:200]}"
        for one in differing
    )


def test_every_control_is_reachable_on_both(comparison):
    """Hit-testing is a by-product of drawing, on both hosts or on neither."""
    assert comparison["chrome_missing"] == []
    assert comparison["chrome_extra"] == []


def test_the_menus_are_the_same_tree(comparison):
    """One `MenuModel`; the hosts render it, they do not each build one."""
    assert comparison["menu_differences"] == []


def test_the_chrome_lands_in_the_same_bands(comparison):
    """Same furniture, same place: a page is not a differently laid-out app."""
    assert comparison["bands_differ"] == {}
