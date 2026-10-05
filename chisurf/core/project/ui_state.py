from __future__ import annotations

import copy
import json
import typing


class ProjectUIStateError(ValueError):
    """The requested document view cannot be captured or published exactly."""


def _fit_window_map(main_window: typing.Any) -> dict[str, typing.Any]:
    """Resolve real document fit windows by scientific identity, never MDI order."""
    mdi = getattr(main_window, "mdiarea", None)
    enumerate_windows = getattr(mdi, "subWindowList", None)
    windows = enumerate_windows() if callable(enumerate_windows) else []
    result = {}
    for window in windows:
        fit = getattr(window, "fit", None)
        if fit is None:
            continue
        uid = getattr(fit, "unique_identifier", None)
        if not isinstance(uid, str) or not uid:
            raise ProjectUIStateError("fit view has no scientific UID")
        if uid in result:
            raise ProjectUIStateError(f"duplicate fit view UID: {uid}")
        result[uid] = window
    return result


def _capture_fit_windows(main_window: typing.Any) -> dict[str, dict]:
    """Capture detached per-fit plot/controller state using explicit view hooks."""
    states = {}
    for uid, window in _fit_window_map(main_window).items():
        capture = getattr(window, "get_project_plot_state", None)
        if not callable(capture):
            raise ProjectUIStateError(f"fit view cannot capture plot state: {uid}")
        try:
            state = capture()
            if not isinstance(state, dict):
                raise ValueError("plot state must be a mapping")
            # Explicit JSON view hooks must not publish controllers, callbacks,
            # or non-finite/opaque values into the scientific document.
            json.dumps(state, allow_nan=False)
            states[uid] = copy.deepcopy(state)
        except Exception as exc:
            raise ProjectUIStateError(f"fit view capture failed for {uid}: {exc}") from exc
    return states


def _prepare_fit_windows(main_window: typing.Any, state: dict) -> list[tuple]:
    """Validate all view targets before allowing any presentation mutation."""
    if "fit_windows" not in state:
        return []
    records = state["fit_windows"]
    if not isinstance(records, dict):
        raise ProjectUIStateError("fit_windows must be a mapping")
    windows = _fit_window_map(main_window)
    prepared = []
    for uid, record in records.items():
        if not isinstance(uid, str) or uid not in windows:
            raise ProjectUIStateError(f"unknown fit view UID: {uid}")
        if not isinstance(record, dict):
            raise ProjectUIStateError(f"invalid plot state for {uid}")
        apply = getattr(windows[uid], "set_project_plot_state", None)
        if not callable(apply):
            raise ProjectUIStateError(f"fit view cannot apply plot state: {uid}")
        prepared.append((uid, apply, copy.deepcopy(record)))
    return prepared


_WINDOW_STATES = ("normal", "maximized", "minimized")


def _capture_arrangement(main_window: typing.Any) -> dict[str, typing.Any] | None:
    """Which fit window is in front, which is active, and how each is shown (by fit UID), from the front end."""
    from chisurf.core.project import ui_layout

    backend = ui_layout.backend_for(main_window)
    if backend is None or backend.capture_arrangement is None:
        return None
    return backend.capture_arrangement(main_window)


def _prepare_arrangement(main_window: typing.Any, state: dict) -> typing.Callable[[], None] | None:
    """Validate the saved window arrangement before any presentation mutation."""
    arrangement = state.get("window_arrangement")
    if arrangement is None:
        return None
    if not isinstance(arrangement, dict):
        raise ProjectUIStateError("window_arrangement must be a mapping")
    windows = _fit_window_map(main_window)
    stacking = arrangement.get("stacking", [])
    states = arrangement.get("window_states", {})
    active = arrangement.get("active")
    view_mode = arrangement.get("view_mode", "windows")
    if not isinstance(stacking, list) or not isinstance(states, dict):
        raise ProjectUIStateError("invalid window_arrangement")
    for uid in [*stacking, *states, *([active] if active is not None else [])]:
        if uid not in windows:
            raise ProjectUIStateError(f"unknown fit view UID: {uid}")
    if any(value not in _WINDOW_STATES for value in states.values()):
        raise ProjectUIStateError("invalid fit window state")
    if view_mode not in ("windows", "tabbed"):
        raise ProjectUIStateError("invalid MDI view mode")

    def apply() -> None:
        from chisurf.core.project import ui_layout

        backend = ui_layout.backend_for(main_window)
        if backend is not None and backend.apply_arrangement is not None:
            backend.apply_arrangement(
                main_window,
                {"stacking": stacking, "active": active, "window_states": states, "view_mode": view_mode},
                windows,
            )

    return apply


def get_ui_state(main_window: typing.Any) -> dict[str, typing.Any]:
    """Capture UI state from main window and all sub-windows.

    Returns a dict with (every part toolkit-neutral; see :mod:`chisurf.core.project.ui_layout`):
    - fit_windows: each fit view's plot state, by fit UID
    - window_arrangement: stacking, active view, window states, view mode, by fit UID
    - layout: main window rectangle, docks by name, fit views by UID
    - backend: optional exact snapshot of the front end that saved it (a hint; other front ends ignore it)
    - active_tabs / active_tab_titles: each main panel's active tab, by index and by title
    """
    state: dict[str, typing.Any] = {}

    if main_window is None:
        return state

    state["fit_windows"] = _capture_fit_windows(main_window)
    arrangement = _capture_arrangement(main_window)
    if arrangement is not None:
        state["window_arrangement"] = arrangement
    state["active_tabs"] = get_active_tabs(main_window)
    if hasattr(main_window, "fit_idx"):
        state["current_fit_index"] = main_window.fit_idx

    # The window layout in toolkit-neutral terms (+ this front end's exact snapshot as a hint), so the project
    # opens whatever front end opens it: see chisurf.core.project.ui_layout.
    from chisurf.core.project import ui_layout

    state.update(ui_layout.capture(main_window))
    state["active_tab_titles"] = get_active_tab_titles(main_window)

    try:
        history_browser = getattr(main_window, "historyBrowser", None)
        get_hist_state = getattr(history_browser, "get_ui_state", None)
        if callable(get_hist_state):
            try:
                state["history_browser"] = get_hist_state()
            except Exception:
                pass
    except Exception:
        pass

    return state


def set_ui_state(main_window: typing.Any, state: dict[str, typing.Any]) -> bool:
    """Apply UI state to main window.

    Returns True if successful, False otherwise.
    """
    if main_window is None:
        return False

    prepared_views = _prepare_fit_windows(main_window, state)
    arrange = _prepare_arrangement(main_window, state)
    success = False
    for uid, apply, record in prepared_views:
        try:
            if apply(record) is False:
                raise ValueError("view rejected saved plot state")
            success = True
        except Exception as exc:
            raise ProjectUIStateError(f"fit view publication failed for {uid}: {exc}") from exc

    from chisurf.core.project import ui_layout

    has_layout = bool(state.get("layout")) or any(
        ui_layout.backend_hint(state, name) for name in ("qt", *(state.get("backend") or {}))
    )
    if has_layout and not ui_layout.restore(main_window, state):
        success = True

    browser_state = state.get("history_browser")
    browser = getattr(main_window, "historyBrowser", None)
    apply_browser = getattr(browser, "set_ui_state", None)
    if isinstance(browser_state, dict) and callable(apply_browser):
        apply_browser(copy.deepcopy(browser_state))
        success = True
    tabs = state.get("active_tabs")
    if isinstance(tabs, dict):
        set_active_tabs(main_window, tabs, state.get("active_tab_titles"))
        success = bool(tabs) or success
    if arrange is not None:
        # Last: per-window geometry and the main window's state are in place.
        arrange()
        success = True
    return success


def get_dataset_selector_state(main_window: typing.Any) -> dict[str, typing.Any]:
    """Get dataset selector state (selection, expanded groups)."""
    state: dict[str, typing.Any] = {}

    if main_window is None:
        return state

    try:
        ds_widget = getattr(main_window, "datasetWidget", None)
        if ds_widget is not None:
            get_state = getattr(ds_widget, "get_selection_state", None)
            if callable(get_state):
                try:
                    state = get_state()
                except Exception:
                    pass
    except Exception:
        pass

    return state


def set_dataset_selector_state(main_window: typing.Any, state: dict[str, typing.Any]) -> bool:
    """Apply dataset selector state."""
    if main_window is None:
        return False

    try:
        ds_widget = getattr(main_window, "datasetWidget", None)
        if ds_widget is not None:
            set_state = getattr(ds_widget, "set_selection_state", None)
            if callable(set_state):
                try:
                    set_state(state)
                    return True
                except Exception:
                    pass
    except Exception:
        pass

    return False


def get_fit_selector_state(main_window: typing.Any) -> dict[str, typing.Any]:
    """Get fit selector state (selected fit group, selected local fit)."""
    state: dict[str, typing.Any] = {}

    if main_window is None:
        return state

    try:
        fit_widget = getattr(main_window, "fitWidget", None)
        if fit_widget is not None:
            get_state = getattr(fit_widget, "get_selection_state", None)
            if callable(get_state):
                try:
                    state = get_state()
                except Exception:
                    pass
    except Exception:
        pass

    return state


def set_fit_selector_state(main_window: typing.Any, state: dict[str, typing.Any]) -> bool:
    """Apply fit selector state."""
    if main_window is None:
        return False

    try:
        fit_widget = getattr(main_window, "fitWidget", None)
        if fit_widget is not None:
            set_state = getattr(fit_widget, "set_selection_state", None)
            if callable(set_state):
                try:
                    set_state(state)
                    return True
                except Exception:
                    pass
    except Exception:
        pass

    return False


def get_active_tabs(main_window: typing.Any) -> dict[str, int]:
    """Get active tab indices for main panels."""
    tabs: dict[str, int] = {}

    if main_window is None:
        return tabs

    panel_names = [
        "datasetPanel",
        "experimentPanel",
        "analysisPanel",
        "plotPanel",
    ]

    for name in panel_names:
        try:
            panel = getattr(main_window, name, None)
            if panel is not None:
                current_idx = getattr(panel, "currentIndex", None)
                if callable(current_idx):
                    tabs[name] = current_idx()
        except Exception:
            pass

    return tabs


def get_active_tab_titles(main_window: typing.Any) -> dict[str, str]:
    """The title of each main panel's active tab: a front end with other tab indices restores by title."""
    titles: dict[str, str] = {}
    for name, idx in get_active_tabs(main_window).items():
        text = getattr(getattr(main_window, name, None), "tabText", None)
        if callable(text):
            try:
                titles[name] = str(text(idx))
            except Exception:
                pass
    return titles


def set_active_tabs(main_window: typing.Any, tabs: dict[str, int], titles: dict[str, str] | None = None) -> None:
    """Set active tabs of the main panels: by saved title where the panel has that tab, else by index."""
    if main_window is None:
        return

    for name, idx in tabs.items():
        try:
            panel = getattr(main_window, name, None)
            if panel is not None:
                title = (titles or {}).get(name)
                count = getattr(panel, "count", None)
                text = getattr(panel, "tabText", None)
                if title and callable(count) and callable(text):
                    match = next((i for i in range(count()) if text(i) == title), None)
                    if match is not None:
                        idx = match
                set_idx = getattr(panel, "setCurrentIndex", None)
                if callable(set_idx):
                    set_idx(idx)
        except Exception:
            pass
