"""The chrome draws through a neutral painter, and it draws the same pixels.

Two claims, and the second is what makes the first safe to have made.

*The panel does not know what a toolkit is.* ``InternalGui`` is a layout and
hit-test engine; it now paints through the six operations in
:mod:`chimol.cmtk.painter`, so it imports with Qt unavailable. That is
the property the browser port needs, and it is checked by blocking the import
rather than by reading the source, because a transitive import is exactly the
kind that gets missed.

*And the pixels did not move.* Replacing thirty-one ``setPen``\\ s, twenty
``setBrush``\\ es and their ``drawRect``/``drawText`` calls with explicit
per-call colours is a refactor, so the images must be **byte-identical** to the
ones captured before it. Asserting anything weaker would let a wiring mistake --
a swapped colour, a dropped hover fill, an alignment flag lost in translation --
pass as "close enough", and those are precisely the mistakes this shape of
change makes.

The baselines are the same PNGs the GPU painter will later be judged against,
by control inventory rather than by pixels. Here they are compared exactly,
because here there is no reason for them to differ.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

#: The baselines were captured under the offscreen platform plugin (see the
#: capture command in :mod:`chrome_baseline`). The repaint is a QPainter
#: rasterisation, so it follows the *ambient* platform otherwise: under a
#: native session plugin the app font is larger and the device pixel ratio is
#: 2, and the same chrome paints different pixels — not a regression, an
#: environment dependence. Pin it here, at import time (before any QApplication
#: exists), so a single-test run matches what the suite and the baseline both
#: use. ``setdefault`` so a runner that pinned something else keeps it.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chisurf.plugins.chimol.test import chrome_baseline

#: Where the committed before-half lives.
_BASELINE = pathlib.Path(chrome_baseline.OUT_DIR)


def test_the_panel_imports_without_a_gui_toolkit():
    """``internal_gui`` and the painter interface load with Qt blocked.

    Run in a subprocess with a meta-path finder that refuses every Qt binding.
    The finder implements ``find_spec``: the ``find_module``/``load_module``
    pair it replaced was **removed in Python 3.12**, and a finder written
    against that older protocol is silently skipped rather than rejected -- so
    the guard passes by doing nothing, and every module appears to import
    without Qt while Qt is in fact right there.
    """
    root = pathlib.Path(__file__).resolve().parents[4]
    script = textwrap.dedent(
        """
        import sys

        _BLOCKED = {"qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6"}


        class _BlockQt:
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split(".")[0] in _BLOCKED:
                    raise ImportError("Qt is blocked: " + fullname)
                return None


        sys.meta_path.insert(0, _BlockQt())

        # The blocker must actually block, or this test proves nothing.
        try:
            import qtpy
        except ImportError:
            pass
        else:
            raise SystemExit("the Qt blocker is a no-op")

        import chimol.renderer.internal_gui  # noqa: F401
        import chimol.cmtk.painter  # noqa: F401
        print("ok")
        """
    )
    # The parent's environment, with the relocated engine prepended -- not a
    # hand-built one. ``internal_gui`` reaches ``object_menus`` and
    # ``mouse_modes``, and those want the same paths the rest of the suite
    # runs with; a minimal env turns a passing guard into an unrelated
    # ImportError that reads like the guard failing.
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(root / "modules" / "chimol"), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(root),
        env=env,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "ok" in result.stdout


@pytest.mark.parametrize("state", chrome_baseline.STATES)
def test_the_chrome_is_unchanged_by_the_painter_interface(state, qapp, tmp_path):
    """Each state repaints byte-identically to its committed baseline."""
    pytest.importorskip("qtpy")
    expected = _BASELINE / f"{state}.png"
    if not expected.exists():
        pytest.skip(f"no baseline for {state}; run chrome_baseline to capture one")

    chrome_baseline.capture(tmp_path)
    got = tmp_path / f"{state}.png"

    assert got.read_bytes() == expected.read_bytes(), (
        f"the {state} chrome changed. If that was intended, look at both "
        f"images before re-capturing: {got} vs {expected}"
    )


def test_no_control_the_baseline_could_reach_has_been_lost(qapp, tmp_path):
    """Every control the baseline could reach is still reachable.

    The inventory, not the image, is what parity is judged on once the GPU
    painter lands -- a glyph atlas moves text metrics on purpose. Pinned here
    so the two halves of the port are compared on the same list.

    **A missing control fails; a new one does not.** The rule this enforces is
    that nothing was *lost*, which is what a migration can silently do. Equality
    was the wrong shape for it: the baseline is the before-half of the painter
    port and cannot be re-captured once that lands -- the PNGs beside it would
    be overwritten with after-images -- so a feature that legitimately adds a
    control had no way past an equality check except by corrupting the record
    it is compared against. Adding `selecting:` (the block's selection-level
    row, which was drawn and unreachable) is what surfaced this.
    """
    expected_path = _BASELINE / "inventory.json"
    if not expected_path.exists():
        pytest.skip("no baseline inventory; run chrome_baseline to capture one")

    chrome_baseline.capture(tmp_path)
    got = json.loads((tmp_path / "inventory.json").read_text(encoding="utf-8"))
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    for state in sorted(expected):
        was = set(expected[state]["reachable"])
        now = set(got[state]["reachable"])
        assert not (was - now), (
            f"{state}: controls the baseline could reach are gone: "
            f"{sorted(was - now)}"
        )


def test_the_disabled_colour_button_greys_the_way_qcolor_did():
    """``_grey_of`` reproduces ``QColor.value() // 3 + 60`` without a toolkit.

    ``value()`` is HSV value -- the largest of the three components -- so every
    fully-saturated rainbow stop greys to the same 145. Pinned because the
    equivalence is the whole reason the hex strings could become tuples.
    """
    from chimol.renderer.internal_gui import (
        COLOR_BUTTON_STOPS,
        _grey_of,
    )

    assert all(_grey_of(stop) == (145, 145, 145) for stop in COLOR_BUTTON_STOPS)
    assert _grey_of((0, 0, 0)) == (60, 60, 60)
