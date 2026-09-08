"""ndX must have its equations before it is handed a burst table.

ndX loads its MFD equations — and the constants they use — in
``_deferred_init``, which runs when its window is first shown. Embedded as step 7
of this workflow it is handed files as soon as the step's context is applied, and
that can happen first. The table then loads with ``equations = []``: every burst
column is present, no error is raised, no plot is empty, and E and S simply do
not exist.

It depends on the order of two unrelated things, which is why it appeared to
come and go.
"""

from __future__ import annotations

import pathlib

import pytest

from chisurf.plugins.burst.alex_suite.gui.tool import AlexSuiteTool


class _Ndx:
    """A window that only records what was pushed onto it."""

    def __init__(self, equations=None):
        self.equations = list(equations or [])
        self.constants = {}


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_equations_are_loaded_when_missing(qapp):
    """Against a real window, because ``load_settings`` touches most of one.

    A stub cannot stand in here: the loader also restores the colormap, the axis
    settings and the equation editor, so faking it would test the fake.
    """
    from ndxplorer.core.plot_main import NDXplorer

    ndx = NDXplorer()                       # never shown: deferred init has not run
    try:
        assert not getattr(ndx, "equations", None), (
            "this test is meaningless if the window already has equations"
        )
        AlexSuiteTool._ensure_ndx_equations(ndx)
        assert len(ndx.equations) > 0, "the burst table would load with no equations"
        assert dict(ndx.constants), "the equations have no constants to evaluate with"
    finally:
        ndx.close()


def test_an_already_loaded_window_is_left_alone():
    """Re-loading would discard equations the user edited in the editor."""
    sentinel = [{"Sg": "'Green Count Rate (KHz)'"}]
    ndx = _Ndx(sentinel)
    AlexSuiteTool._ensure_ndx_equations(ndx)
    assert ndx.equations == sentinel


def test_a_failure_does_not_stop_the_step():
    """Missing settings must not prevent the bursts from opening at all."""

    class _Broken:
        equations = []

        def __setattr__(self, name, value):
            raise RuntimeError("no settings here")

    AlexSuiteTool._ensure_ndx_equations(_Broken())   # must not raise
