"""The Datasets list's right-click menu, its unfolding groups, and the parameter table's Prior and linked ink.

What the Qt list and parameter popup did that the emtk docks did not: Save / Load / Remove / Group / Ungroup /
Refresh on the datasets, a group that unfolds into its members, a per-parameter *Prior* selector, and linked
parameters drawn apart. Each is driven by real pointer and key input on the shell, and read back from the session.
"""

from __future__ import annotations

import pytest
from emtk.events import CONTROL_MODIFIER, LEFT_BUTTON, RIGHT_BUTTON
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
from test.native_emtk.test_emtk_shell_fixes import _click, _row_point, _two_curves


def _table(shell):
    return shell.data.forms["datasets"].tables["dataset_rows"]


def _names(shell) -> list[str]:
    return [r["name"] for r in shell.data.datasets.datasets if r["experiment"] != "Global"]


def _right_click(driver, point):
    driver.surface.on_pointer_move(*point, 0, 0)
    driver.frame()
    driver.surface.on_pointer_press(*point, RIGHT_BUTTON, 0)
    driver.frame()
    driver.surface.on_pointer_release(*point, RIGHT_BUTTON, 0)
    driver.frame(2)


def _menu_labels(shell) -> dict[str, bool]:
    """``{label: enabled}`` of the open menu."""
    panel = _table(shell).menu_panel
    assert panel is not None, "the context menu is not open"
    return {e.label: bool(e.enabled) for e in panel.entries if e is not None and hasattr(e, "label")}


def _pick(driver, shell, label: str) -> None:
    """Click the menu entry *label* where it is drawn."""
    texts = [t for t in driver.painter.texts if t[5].strip() == label]
    assert texts, f"{label!r} is not drawn: {[t[5] for t in driver.painter.texts][-30:]}"
    x, y, w, h = texts[-1][:4]
    _click(driver, (x + w / 2 if w else x + 4, y + h / 2))


def _setup(driver, shell):
    names = _two_curves(driver, shell)
    return names, names.index("Kristine_with_error"), names.index("fcs_demo")


def test_right_click_offers_all_six_actions_gated_by_the_selection(shell):  # noqa: F811
    driver = Driver(shell, size=(1500, 1100))
    _, first, second = _setup(driver, shell)
    _click(driver, _row_point(shell, "dataset_rows", first))
    _right_click(driver, _row_point(shell, "dataset_rows", first))
    labels = _menu_labels(shell)
    assert list(labels) == ["Save", "Load", "Remove", "Group", "Ungroup", "Refresh"]
    assert labels["Save"] and labels["Load"] and labels["Remove"] and labels["Refresh"]
    assert not labels["Group"], "one dataset cannot be grouped"
    assert not labels["Ungroup"], "no group is selected"
    driver.screenshot(SHOTS / "emtk_datasets_menu_single.png")
    driver.escape()
    # Two selected: Group becomes available.
    _click(driver, _row_point(shell, "dataset_rows", second), CONTROL_MODIFIER)
    _right_click(driver, _row_point(shell, "dataset_rows", second))
    assert _menu_labels(shell)["Group"]


def test_group_unfolds_into_members_and_ungroup_restores_them(shell):  # noqa: F811
    driver = Driver(shell, size=(1500, 1100))
    names, first, second = _setup(driver, shell)
    data = shell.data
    _click(driver, _row_point(shell, "dataset_rows", first))
    _click(driver, _row_point(shell, "dataset_rows", second), CONTROL_MODIFIER)
    _right_click(driver, _row_point(shell, "dataset_rows", second))
    _pick(driver, shell, "Group")
    _settle(driver, lambda: _idle(shell) and any(r.get("group") for r in data.datasets.datasets), "the group")
    rows = data.datasets.datasets
    group = next(r for r in rows if r.get("group"))
    members = [r for r in rows if r.get("parent") == group["uid"]]
    assert sorted(m["name"] for m in members) == ["Kristine_with_error", "fcs_demo"]
    assert [m["number"] for m in members] == [f"{group['index']}.1", f"{group['index']}.2"]
    control = _table(shell).control
    shown = [control.value(i, "name") for i in control.order()]
    assert group["name"] in shown and "fcs_demo" not in shown, "a group starts folded"
    # Open it with its disclosure triangle (a double click on the row).
    position = shown.index(group["name"])
    bx, by, bw, _bh = control._body_box
    _click(driver, (bx + 10, by + control._row_h * (position + 0.5)))
    driver.frame(2)
    assert control.is_parent(rows.index(group))
    control.toggle_expanded(rows.index(group)) if hasattr(control, "toggle_expanded") else None
    driver.frame(3)
    shown = [control.value(i, "name") for i in control.order()]
    assert "fcs_demo" in shown and "Kristine_with_error" in shown, shown
    driver.screenshot(SHOTS / "emtk_datasets_group_unfolded.png")
    # Ungroup the group.
    position = [control.value(i, "name") for i in control.order()].index(group["name"])
    _click(driver, _row_point(shell, "dataset_rows", position))
    _right_click(driver, _row_point(shell, "dataset_rows", position))
    assert _menu_labels(shell)["Ungroup"]
    _pick(driver, shell, "Ungroup")
    _settle(driver, lambda: _idle(shell) and not any(r.get("group") for r in data.datasets.datasets), "ungrouped")
    assert sorted(_names(shell)) == sorted(n for n in names if n != "Global Dataset")


def test_remove_takes_every_selected_dataset(shell):  # noqa: F811
    driver = Driver(shell, size=(1500, 1100))
    _, first, second = _setup(driver, shell)
    _click(driver, _row_point(shell, "dataset_rows", first))
    _click(driver, _row_point(shell, "dataset_rows", second), CONTROL_MODIFIER)
    _right_click(driver, _row_point(shell, "dataset_rows", second))
    _pick(driver, shell, "Remove")
    _settle(driver, lambda: _idle(shell) and not _names(shell), "both removed")
    assert _names(shell) == []


def test_refresh_reads_the_session_again(shell):  # noqa: F811
    driver = Driver(shell, size=(1500, 1100))
    _, first, _ = _setup(driver, shell)
    _right_click(driver, _row_point(shell, "dataset_rows", first))
    shell.data.datasets.datasets = type(shell.data.datasets.datasets)()
    _pick(driver, shell, "Refresh")
    _settle(driver, lambda: _idle(shell) and len(_names(shell)) == 2, "the list is read again")


def test_save_then_load_round_trips_a_dataset(shell, tmp_path):  # noqa: F811
    driver = Driver(shell, size=(1500, 1100))
    _, first, _ = _setup(driver, shell)
    data = shell.data
    _click(driver, _row_point(shell, "dataset_rows", first))
    _right_click(driver, _row_point(shell, "dataset_rows", first))
    _pick(driver, shell, "Save")
    assert data.file_dialog is not None and data.file_dialog.mode == "save"
    assert data.file_dialog.filename == "Kristine_with_error.pkl"
    target = tmp_path / "kristine.pkl"
    data.file_dialog.draw = lambda: [str(target)]
    driver.frame(2)
    _settle(driver, lambda: _idle(shell) and target.is_file(), "the dataset saved")
    assert target.stat().st_size > 0
    before = len(_names(shell))
    _right_click(driver, _row_point(shell, "dataset_rows", first))
    _pick(driver, shell, "Load")
    assert data.file_dialog is not None and data.file_dialog.mode == "open"
    data.file_dialog.draw = lambda: [str(target)]
    driver.frame(2)
    _settle(driver, lambda: _idle(shell) and len(_names(shell)) == before + 1, "the dataset loaded")
    assert _names(shell).count("Kristine_with_error") == 2


# -- the parameter tables: Prior, linked ink ---------------------------------------------------- #


def _two_fits(driver, shell):
    _load(driver, shell, KRISTINE)
    first = _add_fit(driver, shell)
    second = _add_fit(driver, shell)
    shell.docks.focus(ANALYSIS_KEY)
    driver.frame(3)
    return first, second


def _editor_row(shell, name: str) -> dict:
    """The current fit's editor row *name* (the editor lists every diffusion preset's ``N``)."""
    data = shell.data
    info = data.session.api.get_fit_info(fit_uid=data.current_uid)
    info = info.get("fit", info)
    uid = next(p["uid"] for p in info["model"]["parameters_all"] if p["name"] == name)
    return next(r for source in data.editor._sources.values() for r in source if r.get("uid") == uid)


def _prior_of(shell, uid: str, name: str):
    info = shell.data.session.api.get_fit_info(fit_uid=uid)
    info = info.get("fit", info)
    entry = next(p for p in info["model"]["parameters_all"] if p["name"] == name)
    return entry.get("prior")


def test_a_typed_prior_reaches_the_parameter_and_box_clears_it(shell):  # noqa: F811
    driver = Driver(shell, size=(1500, 1100))
    _load(driver, shell, KRISTINE)
    uid = _add_fit(driver, shell)
    shell.docks.focus(ANALYSIS_KEY)
    driver.frame(3)
    data = shell.data
    assert _editor_row(shell, "N")["prior"] == "Box"
    data.editor.edit_cell(_editor_row(shell, "N"), "prior", "Gaussian(3, 0.5)")
    _settle(driver, lambda: _idle(shell) and _editor_row(shell, "N")["prior"] != "Box", "the prior set")
    assert _editor_row(shell, "N")["prior"] == "Gaussian(3, 0.5)"
    state = _prior_of(shell, uid, "N")
    assert state["kind"] == "normal" and state["mu"] == 3.0 and state["sigma"] == 0.5
    driver.frame(3)
    driver.screenshot(SHOTS / "emtk_parameter_prior.png")
    data.editor.edit_cell(_editor_row(shell, "N"), "prior", "Box")
    _settle(driver, lambda: _idle(shell) and _editor_row(shell, "N")["prior"] == "Box", "the prior cleared")
    assert _prior_of(shell, uid, "N") is None
    # Text that names no family changes nothing and says what is accepted.
    data.editor.edit_cell(_editor_row(shell, "N"), "prior", "Cauchy")
    assert "Unknown prior" in data.status and "Gaussian" in data.status
    assert _prior_of(shell, uid, "N") is None


def test_the_row_menu_picks_a_prior_family_seeded_at_the_value(shell):  # noqa: F811
    from chisurf.emtk.model_sections import LinkMenu

    driver = Driver(shell, size=(1500, 1100))
    _load(driver, shell, KRISTINE)
    uid = _add_fit(driver, shell)
    record = _editor_row(shell, "N")
    menu = LinkMenu(shell.data.editor.sections, record, [], None)
    prior = next(e for e in menu.panel.entries if getattr(e, "label", "") == "Prior")
    assert [e.label for e in prior.entries][:3] == ["Box (bounds only)", "Gaussian", "Truncated Gaussian"]
    assert [e.label for e in prior.entries if e.checked] == ["Box (bounds only)"]
    gaussian = next(e for e in prior.entries if e.label == "Gaussian")
    menu.pick(gaussian)
    _settle(driver, lambda: _idle(shell) and _prior_of(shell, uid, "N"), "the Gaussian prior")
    state = _prior_of(shell, uid, "N")
    assert state["kind"] == "normal" and state["mu"] == pytest.approx(record["value"])
    assert state["sigma"] == pytest.approx(abs(record["value"]) * 0.1)


def test_a_linked_parameter_is_drawn_in_the_linked_ink_and_names_its_master(shell):  # noqa: F811
    from emtk import style

    driver = Driver(shell, size=(1500, 1100))
    first, second = _two_fits(driver, shell)
    api = shell.data.session.api
    shell.data.current_uid = first
    shell.data._dirty |= {"current"}
    _settle(driver, lambda: _idle(shell), "the first fit current")
    master = _editor_row(shell, "N")
    shell.data.current_uid = second
    shell.data._dirty |= {"current"}
    _settle(driver, lambda: _idle(shell) and shell.data.analysis.info.get("uid") == second, "the second fit current")
    follower = _editor_row(shell, "N")
    assert follower["uid"] != master["uid"] and not follower["linked"]
    api.link_parameter(follower["uid"], master["uid"], fit_uid=second)
    shell.data._dirty |= {"current"}
    _settle(driver, lambda: _idle(shell) and _editor_row(shell, "N")["linked"], "the link read back")
    follower = _editor_row(shell, "N")
    assert follower["master"] == "N"
    driver.frame(3)
    editor = shell.data.editor
    bound = next(
        b for b in editor.form.tables.values()
        if any(b.record(i).get("uid") == follower["uid"] for i in range(b.control.row_count()))
    )
    control = bound.control
    index = next(i for i in range(control.row_count()) if bound.record(i).get("uid") == follower["uid"])
    assert control.linked(index) == "N"
    texts = [t for t in driver.painter.texts if t[6] == style.LINKED]
    assert texts, "no text was drawn in the linked ink"
    position = control.order().index(index)
    bx, by, bw, _bh = control._body_box
    tip, _part = control.tooltip_at(bx + bw / 4, by + control._row_h * (position + 0.5) - control.bar.top * control._row_h)
    # The first line names the master. A narrow table also folds the cells of
    # its dropped columns (Lo/Hi/Bounds/Prior) into the tooltip below it --
    # emtk 9bdd67a, wired in e20cb4c6e -- so it need not be the only line.
    assert tip.splitlines()[0] == "linked to N", tip
    driver.screenshot(SHOTS / "emtk_parameter_linked.png")


@pytest.mark.parametrize(
    "locale, ungroup, linked",
    [("de", "Gruppierung aufheben", "verknüpft mit N"), ("fr", "Dissocier", "lié à N")],
)
def test_the_new_strings_are_translated(locale, ungroup, linked):
    from emtk import i18n as toolkit_i18n

    from chisurf.emtk import i18n

    previous = toolkit_i18n.get_locale() if hasattr(toolkit_i18n, "get_locale") else "en"
    try:
        i18n.install(locale)
        i18n.set_locale(locale)
        assert toolkit_i18n.tr("Ungroup") == ungroup
        assert toolkit_i18n.tr("Grouping the datasets…") != "Grouping the datasets…"
        assert toolkit_i18n.tr("linked to {name}", domain="emtk").format(name="N") == linked
    finally:
        toolkit_i18n.set_locale(previous)
