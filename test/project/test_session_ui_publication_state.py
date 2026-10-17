"""Fit-window document UI is identified by scientific UID, not widget order."""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest


class _Area:
    """The container the project state asks for its fit windows: it only lists them."""

    def __init__(self, windows):
        self._windows = windows

    def subWindowList(self):  # noqa: N802 - the name the project state looks up
        """Return the windows in display order."""
        return list(self._windows)


@pytest.fixture
def native_ui():
    """Build fit views with the supported project plot-state hooks."""
    windows = []
    for uid, selected in (("fit-a", 1), ("fit-b", 0)):
        window = SimpleNamespace(fit=SimpleNamespace(unique_identifier=uid))
        window.project_view = {
            "version": 1,
            "current_plot_index": selected,
            "plots": [{"index": 0, "controller": {"log_x": True, "log_y": False}}],
            "geometry": [20, 30, 800, 500],
        }
        window.get_project_plot_state = lambda view=window: copy.deepcopy(view.project_view)
        window.set_project_plot_state = lambda state, view=window: (
            setattr(view, "project_view", copy.deepcopy(state)) or True
        )
        windows.append(window)
    main = SimpleNamespace(mdiarea=_Area(windows), fit_idx=0)
    return main, windows, None


def test_capture_preserves_each_fit_window_state_without_aliasing(native_ui):
    """An ordinary document snapshot includes every plot/control/tab state."""
    from chisurf.core.project.ui_state import get_ui_state

    main, windows, _app = native_ui
    state = get_ui_state(main)
    assert state["fit_windows"] == {
        "fit-a": windows[0].project_view,
        "fit-b": windows[1].project_view,
    }
    windows[0].project_view["plots"][0]["controller"]["log_x"] = False
    assert state["fit_windows"]["fit-a"]["plots"][0]["controller"]["log_x"] is True


def test_restore_addresses_fit_uid_instead_of_mdi_window_order(native_ui):
    """A reordered session applies each controller only to its actual owner."""
    from chisurf.core.project.ui_state import set_ui_state

    main, windows, _app = native_ui
    saved = {
        "fit_windows": {
            "fit-b": {"version": 1, "current_plot_index": 3},
            "fit-a": {"version": 1, "current_plot_index": 2},
        },
    }
    set_ui_state(main, saved)
    assert windows[0].project_view == saved["fit_windows"]["fit-a"]
    assert windows[1].project_view == saved["fit_windows"]["fit-b"]


def test_capture_does_not_silently_drop_a_failing_plot_state(native_ui):
    """A false-success snapshot must not erase the user's GUI model context."""
    from chisurf.core.project.ui_state import get_ui_state

    main, windows, _app = native_ui

    def fail():
        raise RuntimeError("plot capture failed")

    windows[0].get_project_plot_state = fail
    with pytest.raises(Exception, match="plot capture failed"):
        get_ui_state(main)


def test_restore_propagates_plot_application_failure(native_ui):
    """Owner publication must see failed view restoration and roll back."""
    from chisurf.core.project.ui_state import set_ui_state

    main, windows, _app = native_ui

    def fail(state):
        raise RuntimeError("plot publication failed")

    windows[0].set_project_plot_state = fail
    with pytest.raises(Exception, match="plot publication failed"):
        set_ui_state(main, {"fit_windows": {"fit-a": {"version": 1}}})


def test_unknown_fit_ui_is_rejected_before_any_application(native_ui):
    """A malformed fit UID must not partially mutate existing view state."""
    from chisurf.core.project.ui_state import set_ui_state

    main, windows, _app = native_ui
    before = [copy.deepcopy(window.project_view) for window in windows]
    state = {
        "fit_windows": {
            "fit-a": {"version": 1, "current_plot_index": 4},
            "unowned-fit": {"version": 1, "current_plot_index": 9},
        }
    }
    with pytest.raises(Exception, match="unowned-fit"):
        set_ui_state(main, state)
    assert [window.project_view for window in windows] == before
