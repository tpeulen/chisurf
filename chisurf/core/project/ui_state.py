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


def get_ui_state(main_window: typing.Any) -> dict[str, typing.Any]:
    """Capture UI state from main window and all sub-windows.

    Returns a dict with:
    - main_window: geometry and dock state
    - mdi_area: MDI subwindow layout
    - dataset_selector: current selection and expanded state
    - fit_selector: current selection
    - active_tabs: which tabs are active in each panel
    """
    state: dict[str, typing.Any] = {}

    if main_window is None:
        return state

    state["fit_windows"] = _capture_fit_windows(main_window)
    state["active_tabs"] = get_active_tabs(main_window)
    if hasattr(main_window, "fit_idx"):
        state["current_fit_index"] = main_window.fit_idx

    try:
        save_geom = getattr(main_window, "saveGeometry", None)
        if callable(save_geom):
            try:
                ba = save_geom()
                state["geometry"] = bytes(ba).hex()
            except Exception:
                pass
    except Exception:
        pass

    try:
        save_state = getattr(main_window, "saveState", None)
        if callable(save_state):
            try:
                ba = save_state()
                state["dock_state"] = bytes(ba).hex()
            except Exception:
                pass
    except Exception:
        pass

    try:
        mdi = getattr(main_window, "mdiarea", None)
        if mdi is not None:
            save_mdi = getattr(mdi, "saveState", None)
            if callable(save_mdi):
                try:
                    ba = save_mdi()
                    state["mdi_area"] = {"state": bytes(ba).hex()}
                except Exception:
                    pass
    except Exception:
        pass

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
    success = False
    for uid, apply, record in prepared_views:
        try:
            if apply(record) is False:
                raise ValueError("view rejected saved plot state")
            success = True
        except Exception as exc:
            raise ProjectUIStateError(f"fit view publication failed for {uid}: {exc}") from exc

    try:
        geom_hex = state.get("geometry")
        if geom_hex:
            restore_geom = getattr(main_window, "restoreGeometry", None)
            if callable(restore_geom):
                try:
                    geom_bytes = bytes.fromhex(geom_hex)
                    restore_geom(geom_bytes)
                    success = True
                except Exception:
                    pass
    except Exception:
        pass

    try:
        dock_hex = state.get("dock_state")
        if dock_hex:
            restore_state = getattr(main_window, "restoreState", None)
            if callable(restore_state):
                try:
                    state_bytes = bytes.fromhex(dock_hex)
                    restore_state(state_bytes)
                    success = True
                except Exception:
                    pass
    except Exception:
        pass

    try:
        mdi_state = state.get("mdi_area", {})
        mdi_hex = mdi_state.get("state")
        if mdi_hex:
            mdi = getattr(main_window, "mdiarea", None)
            if mdi is not None:
                restore_mdi = getattr(mdi, "restoreState", None)
                if callable(restore_mdi):
                    try:
                        mdi_bytes = bytes.fromhex(mdi_hex)
                        restore_mdi(mdi_bytes)
                        success = True
                    except Exception:
                        pass
    except Exception:
        pass

    browser_state = state.get("history_browser")
    browser = getattr(main_window, "historyBrowser", None)
    apply_browser = getattr(browser, "set_ui_state", None)
    if isinstance(browser_state, dict) and callable(apply_browser):
        apply_browser(copy.deepcopy(browser_state))
        success = True
    tabs = state.get("active_tabs")
    if isinstance(tabs, dict):
        set_active_tabs(main_window, tabs)
        success = bool(tabs) or success
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


def set_active_tabs(main_window: typing.Any, tabs: dict[str, int]) -> None:
    """Set active tab indices for main panels."""
    if main_window is None:
        return

    for name, idx in tabs.items():
        try:
            panel = getattr(main_window, name, None)
            if panel is not None:
                set_idx = getattr(panel, "setCurrentIndex", None)
                if callable(set_idx):
                    set_idx(idx)
        except Exception:
            pass
