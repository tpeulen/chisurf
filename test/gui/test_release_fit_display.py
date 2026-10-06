"""Completion events refresh their fit windows; link menus show active equations."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest


def _windows():
    """Return two independently counted fit windows and a minimal real-Main receiver."""
    calls = {"A": [], "B": []}

    def sub(uid):
        """Build a window with the same refresh hooks as FitSubWindow."""
        return SimpleNamespace(
            fit=SimpleNamespace(unique_identifier=uid),
            fit_widget=SimpleNamespace(update_chi2=lambda: calls[uid].append("chi2")),
            refresh_current_plot=lambda: calls[uid].append("plot"),
        )

    a, b = sub("A"), sub("B")
    main = SimpleNamespace(
        mdiarea=SimpleNamespace(activeSubWindow=lambda: a, subWindowList=lambda: [a, b])
    )
    return main, calls, a, b


def test_completion_targets_the_payload_owner_even_when_another_window_is_active():
    """An inactive member window receives its own completed curve and statistic."""
    from chisurf.gui.main import Main

    main, calls, _a, _b = _windows()
    Main._refresh_fit_display(main, {"fit_uid": "B"})
    assert calls == {"A": [], "B": ["chi2", "plot"]}


def test_leaf_completion_refreshes_the_window_presenting_its_group():
    """A grouped fit's plot shows a member while the window owns the group UID."""
    from chisurf.gui.main import Main

    main, calls, _a, b = _windows()
    b.fit.grouped_fits = [SimpleNamespace(unique_identifier="B-leaf")]
    Main._refresh_fit_display(main, {"fit_uid": "B-leaf"})
    assert calls == {"A": [], "B": ["chi2", "plot"]}


def test_unknown_owner_does_not_repaint_an_unrelated_window():
    """A late event for a closed window cannot masquerade as an active-fit update."""
    from chisurf.gui.main import Main

    main, calls, _a, _b = _windows()
    Main._refresh_fit_display(main, {"fit_uid": "closed"})
    assert calls == {"A": [], "B": []}


def test_legacy_refresh_without_an_owner_keeps_the_active_window_path():
    """Local callers without an event payload retain their established behavior."""
    from chisurf.gui.main import Main

    main, calls, _a, _b = _windows()
    Main._refresh_fit_display(main)
    assert calls == {"A": ["chi2", "plot"], "B": []}


@pytest.fixture
def equation_session(qapp, monkeypatch):
    """Two real catalogue models exposed through the existing direct RPC client."""
    import chisurf
    from chisurf.core.data import DataCurve
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.fcs.parse import ParseFCSModel
    from chisurf.gui.widgets.fitting import fitting_client
    from chisurf.server.session import SessionState
    from test.gui.test_parameter_link_menu import _DirectClient

    x = np.geomspace(0.001, 100, 64)
    fits = []
    for name in ("A", "B"):
        fit = Fit(
            data=DataCurve(x=x, y=1 + 0.01 / (1 + x), ey=np.full_like(x, 0.01)),
            model_class=ParseFCSModel,
        )
        fit.name = name
        fit.model.model_name = "3D Gauss, 1 bunching"
        fit.model.update()
        fits.append(fit)
    monkeypatch.setattr(chisurf, "fits", fits)
    previous = fitting_client._FITTING_CLIENT
    fitting_client.install_fitting_client(_DirectClient(SessionState(fits=fits)))
    yield fits
    fitting_client._FITTING_CLIENT = previous


def test_catalogue_dto_retains_inactive_ports_and_marks_the_selected_equation(equation_session):
    """Transport retains all topology while supplying six active presentation flags."""
    from chisurf.server.services._stats import _collect_param_list

    fit = equation_session[0]
    entries = _collect_param_list(fit)
    assert len(entries) == len(fit.model.parameters_all) == 134
    active = [entry for entry in entries if entry["active_in_structure"]]
    assert {entry["name"] for entry in active} == {"b", "N", "td", "s", "ba", "bt"}
    # Selection changes visibility, never parameter identity or DTO inventory.
    before = {entry["uid"] for entry in entries}
    fit.model.model_name = fit.model.catalogue_names[1]
    changed = _collect_param_list(fit)
    assert {entry["uid"] for entry in changed} == before
    wanted = set(fit.model.structure_parameter_ids())
    by_uid = {p.unique_identifier: p for p in fit.model.parameters_all}
    assert all(
        entry["active_in_structure"] == (by_uid[entry["uid"]].canonical_id in wanted)
        for entry in changed
    )


def test_link_menu_offers_only_the_active_formula_and_keeps_fixed_targets(equation_session):
    """The unused catalogue's 128 ports cannot drown the equation's six targets."""
    from chisurf.gui.widgets.fitting.parameter_widgets import FittingParameterProxyController
    from test.gui.test_parameter_link_menu import _entries, _fit_menu, _submenu

    source, target = equation_session
    target.model.parameters_all_dict["td"].fixed = True
    controller = FittingParameterProxyController(source.model.parameters_all_dict["td"])
    menu = controller.build_link_menu()
    entries = _entries(_submenu(_fit_menu(menu, "B"), "All parameters"))
    assert set(entries) == {"b", "N", "td", "s", "ba", "bt"}
    assert len(entries) == 6


def test_legacy_parameter_dtos_default_to_visible(qapp):
    """Older transports still populate the menu when they lack additive metadata."""
    from qtpy import QtWidgets

    from chisurf.core.fitting.parameter import FittingParameter
    from chisurf.gui.widgets.fitting.parameter_widgets import FittingParameterProxyController
    from test.gui.test_parameter_link_menu import _entries

    controller = FittingParameterProxyController(FittingParameter(name="source"))
    menu = QtWidgets.QMenu(controller)
    controller._fill_link_targets(
        menu, [{"name": "legacy", "uid": "target"}], {"uid": "fit"}, "source", None
    )
    assert "legacy" in _entries(menu)
