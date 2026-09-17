"""``bg_color`` — a command that did nothing and said nothing.

Three layers had to line up for this to fail silently, which is why it survived:

* the command layer's colour parser returns a **numpy array**;
* the renderer tested ``isinstance(color, (tuple, list))``, which an ndarray is
  not, so it fell through to ``QColor(ndarray)`` — and that raises;
* ``Viewer.set_background_color`` wrapped the call in ``except Exception: pass``.

So the exception was swallowed, no message was emitted, and ``bg_color white``
reported success while changing nothing. The tests below assert the *pixel*,
because that is the only thing that could not have been faked by any of the three.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

_PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test"
    / "data"
    / "atomic_coordinates"
    / "pdb_files"
    / "148l.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    pytest.importorskip("chisurf.core.structure")
    from chimol.hosts.qt.window import MolViewPluginWindow

    win = MolViewPluginWindow()
    shared = win.cmd
    win.resize(700, 500)
    win.show()
    for _ in range(12):
        qapp.processEvents()
    win.load_structure_from_path(_PDB)
    for _ in range(20):
        qapp.processEvents()

    messages: list[str] = []
    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(messages.append)
    shared.set_error_callback(errors.append)

    def do(line: str) -> None:
        shared.do(line)
        for _ in range(10):
            qapp.processEvents()

    yield win.viewer, do, messages, errors
    win.close()


def _background(viewer):
    return tuple(float(c) for c in viewer.renderer._background)


def test_a_named_colour_reaches_the_renderer(session):
    """The whole bug in one assertion: the clear colour must actually change."""
    viewer, do, _messages, errors = session
    assert _background(viewer)[:3] == (0.0, 0.0, 0.0)
    do("bg_color white")
    assert errors == []
    assert _background(viewer)[:3] == (1.0, 1.0, 1.0)


def test_another_colour(session):
    viewer, do, _messages, errors = session
    do("bg_color red")
    assert errors == []
    red, green, blue = _background(viewer)[:3]
    assert red > 0.9 and green < 0.1 and blue < 0.1


def test_a_numpy_array_is_accepted(session):
    """The exact type the command layer hands over.

    A sequence test by `isinstance(tuple, list)` rejects it, which is what sent
    the value into `QColor(ndarray)` and made the whole thing raise.
    """
    viewer, _do, _messages, _errors = session
    assert viewer.set_background_color(np.array([0.25, 0.5, 0.75, 1.0])) is not False
    red, green, blue = _background(viewer)[:3]
    assert (red, green, blue) == pytest.approx((0.25, 0.5, 0.75), abs=1e-6)


def test_a_plain_tuple_still_works(session):
    """The path that did work must not regress while the other is fixed."""
    viewer, _do, _messages, _errors = session
    viewer.set_background_color((0.0, 1.0, 0.0, 1.0))
    assert _background(viewer)[:3] == pytest.approx((0.0, 1.0, 0.0), abs=1e-6)


def test_a_three_component_colour_gets_full_alpha(session):
    viewer, _do, _messages, _errors = session
    viewer.set_background_color([0.1, 0.2, 0.3])
    assert _background(viewer)[3] == pytest.approx(1.0)


def test_the_command_says_what_it_did(session):
    """Silence is what let this hide: the command emitted nothing either way."""
    viewer, do, messages, errors = session
    messages.clear()
    do("bg_color white")
    assert errors == []
    assert messages and "white" in messages[-1]


def test_an_unusable_colour_is_reported(session):
    viewer, do, _messages, errors = session
    do("bg_color notacolouratall")
    assert errors, "an unparseable colour must be reported, not ignored"


def test_a_failure_to_apply_returns_false_rather_than_passing(session):
    """`Viewer.set_background_color` used to swallow every exception.

    It now reports, which is what makes the command able to say it failed.
    """
    viewer, _do, _messages, _errors = session
    saved = viewer.renderer
    try:
        viewer.renderer = None
        assert viewer.set_background_color((1.0, 1.0, 1.0, 1.0)) is False
    finally:
        viewer.renderer = saved
