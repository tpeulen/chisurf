"""The chrome draws through a neutral painter, and it draws the same pixels.

Two claims, and the second is what makes the first safe to have made.

*The panel does not know what a toolkit is.* ``InternalGui`` is a layout and
hit-test engine; it now paints through the six operations in
:mod:`emtk.painter`, so it imports with Qt unavailable. That is
the property the browser port needs, and it is checked by blocking the import
rather than by reading the source, because a transitive import is exactly the
kind that gets missed.

*And nothing was lost.* The QPainter chrome was photographed per state before
the quad painter replaced it (:data:`chrome_baseline.BASELINE_DIR`, frozen;
while both painters existed this file asserted the QPainter repaint
byte-identical to those PNGs). The painter that draws now is judged against
them by **control inventory**, not by pixels: a glyph atlas moves text metrics
on purpose, and what must not change is what is there and reachable.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

from chisurf.plugins.chimol.test import chrome_baseline

#: Where the committed, frozen before-half lives.
_BASELINE = pathlib.Path(chrome_baseline.BASELINE_DIR)


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
            __import__("qtpy")  # the blocker must refuse this
        except ImportError:
            pass
        else:
            raise SystemExit("the Qt blocker is a no-op")

        import chimol.ui.gui  # noqa: F401
        import emtk.painter  # noqa: F401
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


@pytest.fixture(scope="module")
def captured(tmp_path_factory):
    """One capture of every state through the quad painter (no toolkit, no GPU)."""
    pytest.importorskip("PIL")
    out = tmp_path_factory.mktemp("chrome_quads")
    try:
        record = chrome_baseline.capture(out)
    except FileNotFoundError as exc:  # the glyph atlas is not baked here
        pytest.skip(str(exc))
    return out, record


@pytest.mark.parametrize("state", chrome_baseline.STATES)
def test_every_frozen_state_is_photographed_again_at_its_size(state, captured):
    """Each QPainter state has its quad-painter photograph, same size, with ink in it."""
    import numpy as np
    from PIL import Image

    out, _record = captured
    expected = _BASELINE / f"{state}.png"
    if not expected.exists():
        pytest.skip(f"no frozen baseline for {state}")
    got = np.asarray(Image.open(out / f"{state}.png"))
    before = Image.open(expected)
    assert (got.shape[1], got.shape[0]) == before.size
    assert got[..., 3].max() > 0, f"the {state} chrome painted nothing"


def test_the_capture_never_writes_the_frozen_baseline():
    with pytest.raises(ValueError, match="frozen"):
        chrome_baseline.capture(_BASELINE)


def test_no_control_the_baseline_could_reach_has_been_lost(captured):
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
        pytest.skip("no baseline inventory")

    out, _record = captured
    got = json.loads((out / "inventory.json").read_text(encoding="utf-8"))
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    for state in sorted(expected):
        was = set(expected[state]["reachable"])
        now = set(got[state]["reachable"])
        assert not (was - now), (
            f"{state}: controls the baseline could reach are gone: {sorted(was - now)}"
        )


def test_the_disabled_colour_button_greys_the_way_qcolor_did():
    """``_grey_of`` reproduces ``QColor.value() // 3 + 60`` without a toolkit.

    ``value()`` is HSV value -- the largest of the three components -- so every
    fully-saturated rainbow stop greys to the same 145. Pinned because the
    equivalence is the whole reason the hex strings could become tuples.
    """
    from chimol.ui.gui import COLOR_BUTTON_STOPS, _grey_of

    assert all(_grey_of(stop) == (145, 145, 145) for stop in COLOR_BUTTON_STOPS)
    assert _grey_of((0, 0, 0)) == (60, 60, 60)
