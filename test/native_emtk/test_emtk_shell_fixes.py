"""Defects the screenshot lane found in the emtk shell, each driven through real input.

Multi-select in the Datasets dock, member fit windows redrawing after a global fit, the *Link to* menu
listing only the equation's parameters, *Tile Windows* giving usable tiles, the Analysis dock following the
focused tile, and a programmatic dataset selection drawn highlighted.
"""

from __future__ import annotations

import pytest
from emtk.testing import Driver

from chisurf.emtk.fit_docks import ANALYSIS_KEY, DATASETS_KEY
from test.native_emtk.test_emtk_shell_fits import (  # noqa: F401  (the fixture and the helpers)
    KRISTINE,
    MODEL,
    SHOTS,
    _add_fit,
    _idle,
    _load,
    _settle,
    shell,
)


def test_the_link_menu_lists_the_equations_parameters_not_the_catalogue(shell):  # noqa: F811
    from chisurf.emtk.model_sections import LinkMenu

    driver = Driver(shell, size=(1500, 1100))
    _load(driver, shell, KRISTINE)
    first = _add_fit(driver, shell, "Parse-Model")
    second = _add_fit(driver, shell, "Parse-Model")
    api = shell.data.session.api
    info = api.get_fit_info(fit_uid=first)
    info = info.get("fit", info)
    everything = info["model"]["parameters_all"]
    active = [p["name"] for p in everything if p.get("active_in_structure", True)]
    assert len(active) < len(everything), "the model has catalogue ports beyond its equation"
    fits = []
    shell.data.read_fits_for_links(fits.extend)
    _settle(driver, lambda: _idle(shell) and fits, "the fits read")
    record = next(p for p in shell.data.analysis.parameters if p["name"] == "N")
    menu = LinkMenu(shell.data.editor.sections, record, fits, None)
    top = menu.panel.entries[0]
    target = next(e for e in top.entries if e.label == next(f["name"] for f in fits if f["uid"] == first))
    offered = [e.label for e in target.entries]
    assert offered and set(offered) <= set(active) | {record["name"]}
    assert sorted(offered) == sorted(n for n in active if n != record["name"] or first != second)


def _row_point(shell, table: str, position: int) -> tuple[float, float]:
    """A point on row *position* of the Datasets dock's *table*, from the control's drawn box."""
    control = shell.data.forms["datasets"].tables[table].control
    bx, by, bw, _bh = control._body_box
    return bx + bw / 3, by + control._row_h * (position + 0.5)


def _click(driver, point, modifiers=0):
    from emtk.events import LEFT_BUTTON

    driver.surface.on_pointer_move(*point, 0, 0)
    driver.frame()
    driver.surface.on_pointer_press(*point, LEFT_BUTTON, modifiers)
    driver.frame()
    driver.surface.on_pointer_release(*point, LEFT_BUTTON, modifiers)
    driver.frame(2)


def _two_curves(driver, shell):
    from chisurf.core.experiments.fcs.demo import DEMO, make_demo

    _load(driver, shell, KRISTINE)
    _load(driver, shell, make_demo(), DEMO["experiment"], DEMO["reader"])
    shell.docks.focus(DATASETS_KEY)
    driver.frame(3)
    return [r["name"] for r in shell.data.datasets.datasets]


def test_ctrl_click_selects_several_datasets_and_add_analysis_fits_each(shell):  # noqa: F811
    """+ Analysis with two curves selected makes one fit per curve (the Qt macro's rule), not one."""
    from emtk.events import CONTROL_MODIFIER

    driver = Driver(shell, size=(1500, 1100))
    names = _two_curves(driver, shell)
    data = shell.data
    first, second = names.index("Kristine_with_error"), names.index("fcs_demo")
    _click(driver, _row_point(shell, "dataset_rows", first))
    _click(driver, _row_point(shell, "dataset_rows", second), CONTROL_MODIFIER)
    assert [r["name"] for r in data.datasets.selection] == ["Kristine_with_error", "fcs_demo"]
    control = data.forms["datasets"].tables["dataset_rows"].control
    assert control.selected_indices() == [first, second], "both rows are drawn selected"
    driver.screenshot(SHOTS / "emtk_fix_multiselect.png")
    data.datasets.model = MODEL
    driver.click("datasets.add_fit")
    _settle(driver, lambda: _idle(shell) and len(data.windows) == 2, "one fit per curve")
    fitted = sorted(f["data"] for f in data.datasets.fits)
    assert fitted == ["Kristine_with_error", "fcs_demo"]


def test_a_single_click_still_fits_just_that_dataset(shell):  # noqa: F811
    driver = Driver(shell, size=(1500, 1100))
    names = _two_curves(driver, shell)
    data = shell.data
    _click(driver, _row_point(shell, "dataset_rows", names.index("Kristine_with_error")))
    data.datasets.model = MODEL
    driver.click("datasets.add_fit")
    _settle(driver, lambda: _idle(shell) and len(data.windows) == 1, "one fit")
    assert [f["data"] for f in data.datasets.fits] == ["Kristine_with_error"]


def test_a_dataset_selected_by_the_program_is_drawn_selected(shell):  # noqa: F811
    """``select_dataset`` and the drawn highlight read one selection (the table's), not two."""
    driver = Driver(shell, size=(1500, 1100))
    names = _two_curves(driver, shell)
    data = shell.data
    control = data.forms["datasets"].tables["dataset_rows"].control
    other = names.index("Kristine_with_error")
    data.datasets.select_dataset(data.datasets.datasets[other])
    driver.frame(3)
    assert [data.datasets.datasets[i]["name"] for i in control.selected_indices()] == [
        "Kristine_with_error"
    ]
    again = names.index("fcs_demo")
    data.datasets.select_dataset(data.datasets.datasets[again])
    driver.frame(3)
    assert [data.datasets.datasets[i]["name"] for i in control.selected_indices()] == ["fcs_demo"]
    driver.screenshot(SHOTS / "emtk_fix_program_select.png")


def _global_over_two_fits(driver, shell):
    """Two local fits and a Global fit over them, as the Local fits table builds it; their uids."""
    from chisurf.core.experiments.fcs.demo import DEMO, make_demo
    from test.native_emtk.test_emtk_shell_fits import _show_analysis

    data = shell.data
    _load(driver, shell, KRISTINE)
    first = _add_fit(driver, shell)
    _load(driver, shell, make_demo(), DEMO["experiment"], DEMO["reader"])
    second = _add_fit(driver, shell)
    names = {f["uid"]: f["name"] for f in data.session.api.list_fits()}
    data.datasets.select_dataset(data.datasets.datasets[0])
    global_uid = _add_fit(driver, shell, model="Global fit")
    _show_analysis(shell, driver)
    editor = data.editor
    candidate = editor.control_for("selected_candidate_fit")
    add = editor.action_for("press", "add_selected_fit")
    for uid in (first, second):
        setattr(editor, candidate, names[uid])
        _settle(driver, lambda: _idle(shell), "the candidate")
        driver.click(f"editor.{add}")
        _settle(driver, lambda: _idle(shell), "the fit added")
    return global_uid, first, second


def test_member_fit_windows_redraw_when_the_global_fit_finishes(shell):  # noqa: F811
    """A global fit moves its members' parameters; their windows were told only about the global fit.

    The log interleaves the events the shell handles with the refreshes its windows get: after the
    global fit's ``fit.ran`` every member window must be refreshed again, by that event.
    """
    driver = Driver(shell, size=(1500, 1400))
    data = shell.data
    global_uid, first, second = _global_over_two_fits(driver, shell)
    log: list = []
    callbacks = data.session.events._callbacks[""]
    handler = callbacks[callbacks.index(data._on_event)]

    def logged(payload, handler=handler):
        log.append(("event", payload.get("topic"), str(payload.get("fit_uid") or "")))
        handler(payload)

    callbacks[callbacks.index(handler)] = logged
    for uid, window in data.windows.items():
        original = window.refresh

        def counted(uid=uid, original=original):
            log.append(("refresh", uid))
            original()

        window.refresh = counted
    data.show_fit(global_uid)
    _settle(driver, lambda: _idle(shell) and data.current_uid == global_uid, "the global fit shown")
    chi2 = data.analysis.info.get("chi2r_current")
    driver.click("analysis.run_fit")
    _settle(
        driver,
        lambda: _idle(shell) and data.analysis.info.get("chi2r_current") != chi2,
        "the global fit",
        timeout=600.0,
    )
    driver.frame(3)
    ran = max(i for i, entry in enumerate(log) if entry[:2] == ("event", "fit.ran"))
    for uid in (first, second):
        assert ("refresh", uid) in log[ran:], f"member {uid} was not refreshed after fit.ran"


def test_a_global_fit_run_does_not_change_the_structure_it_froze(shell, caplog):  # noqa: F811
    """A global fit over fits that are themselves groups froze only the first level of models, so every
    objective evaluation re-ran ``find_parameters`` on the inner ones and bumped the structure counter:
    "frozen_structure: the parameter structure changed during a run that declared it fixed"."""
    import logging

    driver = Driver(shell, size=(1500, 1400))
    data = shell.data
    global_uid, first, second = _global_over_two_fits(driver, shell)
    data.show_fit(global_uid)
    _settle(driver, lambda: _idle(shell) and data.current_uid == global_uid, "the global fit shown")
    chi2 = data.analysis.info.get("chi2r_current")
    with caplog.at_level(logging.WARNING):
        driver.click("analysis.run_fit")
        _settle(
            driver,
            lambda: _idle(shell) and data.analysis.info.get("chi2r_current") != chi2,
            "the global fit",
            timeout=600.0,
        )
    assert not [r for r in caplog.records if "frozen_structure" in r.getMessage()]


def test_a_global_fit_over_curves_of_different_length_can_be_captured(shell):  # noqa: F811
    """``GlobalFitModel.y`` stacked unequal rows with ``np.array``, which raises; every history record,
    autosave and save of such a session failed ("Recording the change… failed: inhomogeneous shape")."""
    driver = Driver(shell, size=(1500, 1400))
    _global_over_two_fits(driver, shell)
    project = shell.data.session.api.capture_project("global")
    assert project is not None


def _six_fits(driver, shell):
    _load(driver, shell, KRISTINE)
    api = shell.data.session.api
    uids = [api.add_fit([1], model_name=MODEL)["uid"] for _ in range(6)]
    _settle(driver, lambda: _idle(shell) and len(shell.data.windows) == 6, "six windows")
    return uids


def test_tile_windows_makes_a_grid_of_usable_tiles(shell):  # noqa: F811
    from chisurf.emtk.main_app import MIN_TILE

    driver = Driver(shell, size=(1700, 1100))
    _six_fits(driver, shell)
    shell.docks.hide("start")
    shell.tile_windows()
    driver.frame(4)
    boxes = [shell.docks.window(w.key).frame for w in shell.data.windows.values()]
    assert all(box is not None for box in boxes)
    assert len({tuple(b) for b in boxes}) == 6, "every window has a tile of its own"
    assert min(b[2] for b in boxes) >= MIN_TILE[0] and min(b[3] for b in boxes) >= MIN_TILE[1]
    driver.screenshot(SHOTS / "emtk_fix_tile_six.png")


def test_tile_windows_minimizes_what_does_not_fit(shell):  # noqa: F811
    from chisurf.emtk.main_app import MIN_TILE

    driver = Driver(shell, size=(900, 700))
    _six_fits(driver, shell)
    shell.docks.hide("start")
    shell.tile_windows()
    driver.frame(4)
    windows = [shell.docks.window(w.key) for w in shell.data.windows.values()]
    drawn = [w.frame for w in windows if w.frame is not None]
    assert 1 <= len(drawn) < 6
    assert all(w.minimized for w in windows if w.frame is None), "the rest wait on the workspace's strip"
    assert min(b[2] for b in drawn) >= MIN_TILE[0] and min(b[3] for b in drawn) >= MIN_TILE[1]
    driver.screenshot(SHOTS / "emtk_fix_tile_tabs.png")


def test_tile_grid_is_near_square():
    from chisurf.emtk.main_app import tile_grid

    assert tile_grid(6, 1700, 900) == (2, 3)
    assert tile_grid(4, 1200, 800) == (2, 2)
    assert tile_grid(2, 1200, 800) == (1, 2)
    assert tile_grid(6, 400, 300) == (1, 1)


def test_pressing_in_another_tile_makes_it_the_analysis_docks_fit(shell):  # noqa: F811
    driver = Driver(shell, size=(1700, 1100))
    uids = _six_fits(driver, shell)
    data = shell.data
    shell.docks.hide("start")
    shell.tile_windows()
    driver.frame(4)
    for uid in (uids[4], uids[1], uids[5]):
        x, y, w, h = shell.docks.window(data.windows[uid].key).content
        _click(driver, (x + w / 2, y + 12.0))
        _settle(driver, lambda: _idle(shell) and data.current_uid == uid, f"tile {uid} current")
        assert data.analysis.info.get("uid") == uid
    driver.screenshot(SHOTS / "emtk_fix_tile_focus.png")


def test_fits_of_the_same_name_have_distinguishable_window_titles(shell):  # noqa: F811
    driver = Driver(shell, size=(1700, 1100))
    uids = _six_fits(driver, shell)[:2]
    data = shell.data
    titles = [shell.docks.window(data.windows[u].key).title for u in uids]
    assert len(set(titles)) == 2, titles
    assert all(t.startswith(data.datasets.fits[0]["name"]) for t in titles)
    rows = {r["uid"]: r["label"] for r in data.datasets.fits}
    assert [rows[u] for u in uids] == titles
    # removing all but one gives the survivor its plain name back
    api = data.session.api
    api.remove_fits(fit_uids=[u for u in rows if u != uids[0]])
    _settle(driver, lambda: _idle(shell) and len(data.windows) == 1, "one window left")
    assert shell.docks.window(data.windows[uids[0]].key).title == data.datasets.fits[0]["name"]
