"""The "link this parameter to …" context menu.

Reported from a live session: right-clicking a parameter and walking
**Link X to → <fit> → All parameters** produced an empty submenu. The menu was
rendering an empty DTO faithfully, and three separate defects could each empty
it or hide the target the user wanted, so the whole menu is pinned here rather
than only the parameter list.

The fitting client is backed by the service functions directly, which exercises
the same DTO path as ZMQ without needing a server.
"""
from __future__ import annotations

import numpy as np
import pytest
from qtpy import QtWidgets

import chisurf
import chisurf.core.data as data
from chisurf.core.fitting.fit import FitGroup
from chisurf.core.models.description import tcspc_lifetime as LifetimeModel
from chisurf.gui.widgets.fitting.fitting_client import install_fitting_client
from chisurf.gui.widgets.fitting.parameter_widgets import FittingParameterProxyController
from chisurf.server.services.fits import get_fit_info, list_fits
from chisurf.server.services.parameters import parameter_link
from chisurf.server.session import SessionState


def _fit(name: str, n_curves: int = 1) -> FitGroup:
    """Build a TCSPC fit group over *n_curves* synthetic decays."""
    curves = []
    for i in range(n_curves):
        x = np.arange(1, 64, dtype=np.float64)
        y = 1000.0 * np.exp(-x / 10.0) + 1.0
        curves.append(data.DataCurve(x=x, y=y, ey=np.sqrt(y), name=f"{name}-{i}"))
    return FitGroup(
        data=data.DataCurveGroup(curves, name=name),
        model_class=LifetimeModel,
    )


class _DirectClient:
    """Dispatch RPC calls straight into the services, no transport."""

    def __init__(self, state: SessionState):
        self._state = state

    def call(self, method: str, params: dict):
        if method == "fit.list":
            return list_fits(self._state)
        if method == "fit.get":
            return get_fit_info(self._state, **params)
        if method == "parameter.link":
            return parameter_link(self._state, **params)
        raise AssertionError(f"unexpected RPC call {method}")


@pytest.fixture
def session(qapp, monkeypatch):
    """Two fits — one single-curve, one with two curves — behind a fitting client."""
    fits = [_fit("A"), _fit("B", n_curves=2)]
    state = SessionState(fits=fits)
    install_fitting_client(_DirectClient(state))
    monkeypatch.setattr(chisurf, "fits", fits, raising=False)
    try:
        yield fits
    finally:
        install_fitting_client(None)


def _entries(menu: QtWidgets.QMenu) -> list[str]:
    """Every leaf action text below *menu*."""
    out: list[str] = []
    for action in menu.actions():
        if action.menu() is not None:
            out += _entries(action.menu())
        elif not action.isSeparator():
            out.append(action.text())
    return out


def _submenu(menu: QtWidgets.QMenu, title: str) -> QtWidgets.QMenu:
    for action in menu.actions():
        if action.menu() is not None and action.text() == title:
            return action.menu()
    raise AssertionError(f"no submenu {title!r} in {[a.text() for a in menu.actions()]}")


def _fit_menu(menu: QtWidgets.QMenu, suffix: str) -> QtWidgets.QMenu:
    for action in menu.actions():
        if action.menu() is not None and action.text().endswith(suffix):
            return action.menu()
    raise AssertionError(f"no fit entry ending in {suffix!r}")


def test_menu_offers_the_parameters_of_a_fresh_fit(session):
    """The reported bug: the target list came up empty."""
    source = session[0].model.parameters_all_dict["scatter"]
    menu = FittingParameterProxyController(source).build_link_menu()
    all_parameters = _submenu(_fit_menu(menu, "- A"), "All parameters")
    assert len(_entries(all_parameters)) > 1


def test_the_source_parameter_is_the_only_one_excluded(session):
    """Its twin in another fit is a link target; only the clicked one is not."""
    source = session[0].model.parameters_all_dict["scatter"]
    menu = FittingParameterProxyController(source).build_link_menu()
    assert "scatter" not in _entries(_fit_menu(menu, "- A"))
    assert "scatter" in _entries(_fit_menu(menu, "- B"))


def test_targets_are_grouped_as_the_model_presents_them(session):
    """Not one flat list: the model's sub-groups are their own submenus."""
    source = session[0].model.parameters_all_dict["scatter"]
    menu = FittingParameterProxyController(source).build_link_menu()
    fit_menu = _fit_menu(menu, "- A")
    titles = {a.text() for a in fit_menu.actions() if a.menu() is not None}
    assert "All parameters" in titles
    assert titles - {"All parameters"}
    # The menu titles the groups uniformly.
    assert all(title[:1] == title[:1].upper() for title in titles)
    grouped = _submenu(fit_menu, "Instrument")
    assert "timeshift" in _entries(grouped)


def test_every_curve_of_a_group_is_offered(session):
    """A fit group answers ``model`` with one member; all of them are targets."""
    source = session[0].model.parameters_all_dict["scatter"]
    menu = FittingParameterProxyController(source).build_link_menu()
    members = [a.text() for a in _fit_menu(menu, "- B").actions() if a.menu() is not None]
    assert len(members) == 2


def test_triggering_an_entry_links_to_that_parameter(session):
    """Clicking the twin in the other fit links to *that* parameter."""
    source, other = session[0], session[1]
    parameter = source.model.parameters_all_dict["scatter"]
    menu = FittingParameterProxyController(parameter).build_link_menu()
    member = [a for a in _fit_menu(menu, "- B").actions() if a.menu() is not None][0].menu()
    target = [a for a in _submenu(member, "All parameters").actions() if a.text() == "scatter"][0]

    target.trigger()

    assert parameter.is_linked
    assert parameter.link is other.grouped_fits[0].model.parameters_all_dict["scatter"]


def test_a_fit_without_parameters_says_so(session, monkeypatch):
    """An empty popup reads as a broken menu; the menu names the condition."""
    # "walked, owns nothing" — the state a model with no parameters is in.
    monkeypatch.setattr(session[0].model, "_parameters", [])
    parameter = session[1].grouped_fits[0].model.parameters_all_dict["scatter"]
    menu = FittingParameterProxyController(parameter).build_link_menu()
    assert _entries(_fit_menu(menu, "- A")) == ["(no parameters)"]
