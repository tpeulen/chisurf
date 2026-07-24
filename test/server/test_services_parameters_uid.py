from __future__ import annotations

"""UUID-addressed parameter service tests (out-of-fit parameters).

These exercise the ``parameter_uid`` / ``owner_uid`` resolution path added so
parameters that live outside ``chisurf.fits`` (e.g. a plugin working model) can
be read, edited and linked through the same service as fit parameters. Real
:class:`FittingParameter` / :class:`FittingParameterGroup` objects are required
because resolution goes through the global ``Base._uuid_index``.
"""

import pathlib

import utils

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

import chisurf.core.parameter  # noqa: F401  (initialises chisurf.core.settings)
import chisurf.core.models  # noqa: F401
import chisurf.core.fitting.parameter as fp
from chisurf.server.services.parameters import (
    get_parameter,
    set_parameter_value,
    set_parameter_fixed,
    parameter_link,
    parameter_unlink,
)
from chisurf.server.session import SessionState


def _group(names):
    g = fp.FittingParameterGroup()
    for n in names:
        setattr(g, "_" + n, fp.FittingParameter(value=1.0, name=n))
    g.find_parameters()
    return g


class TestParameterUidPath:

    def test_get_by_parameter_uid(self):
        g = _group(["tau"])
        p = g.parameters_all_dict["tau"]
        p.value = 3.5
        state = SessionState(fits=[])
        result = get_parameter(state, parameter_uid=p.unique_identifier)
        assert result["ok"]
        assert result["parameter"]["value"] == 3.5
        assert result["parameter"]["name"] == "tau"

    def test_get_unknown_uid(self):
        state = SessionState(fits=[])
        result = get_parameter(state, parameter_uid="does-not-exist")
        assert not result["ok"]

    def test_set_value_by_uid(self):
        g = _group(["tau"])
        p = g.parameters_all_dict["tau"]
        state = SessionState(fits=[])
        result = set_parameter_value(
            state, value=7.0,
            parameter_uid=p.unique_identifier,
            owner_uid=g.unique_identifier,
        )
        assert result["ok"]
        assert p.value == 7.0

    def test_set_fixed_by_uid(self):
        g = _group(["tau"])
        p = g.parameters_all_dict["tau"]
        p.fixed = False
        state = SessionState(fits=[])
        result = set_parameter_fixed(
            state, fixed=True, parameter_uid=p.unique_identifier,
        )
        assert result["ok"]
        assert p.fixed is True

    def test_link_two_out_of_fit_params_by_uid(self):
        g_master = _group(["m"])
        g_follower = _group(["f"])
        master = g_master.parameters_all_dict["m"]
        follower = g_follower.parameters_all_dict["f"]
        state = SessionState(fits=[])

        result = parameter_link(
            state,
            parameter_uid=follower.unique_identifier,
            owner_uid=g_follower.unique_identifier,
            target_parameter_uid=master.unique_identifier,
        )
        assert result["ok"]
        assert follower.is_linked
        assert follower.link is master

    def test_link_out_of_fit_to_fit_param_by_uid(self):
        # A "fit" whose model is a real group, plus a separate out-of-fit group.
        fit_model = _group(["global_tau"])
        plugin_group = _group(["tau"])
        fit_param = fit_model.parameters_all_dict["global_tau"]
        plugin_param = plugin_group.parameters_all_dict["tau"]

        class _Fit:
            model = fit_model
            unique_identifier = fit_model.unique_identifier

        state = SessionState(fits=[_Fit()])

        # Link the plugin parameter (out of fit) to the fit parameter by UUID.
        result = parameter_link(
            state,
            parameter_uid=plugin_param.unique_identifier,
            owner_uid=plugin_group.unique_identifier,
            target_parameter_uid=fit_param.unique_identifier,
        )
        assert result["ok"]
        assert plugin_param.is_linked
        assert plugin_param.link is fit_param

    def test_unlink_by_uid(self):
        g_master = _group(["m"])
        g_follower = _group(["f"])
        master = g_master.parameters_all_dict["m"]
        follower = g_follower.parameters_all_dict["f"]
        follower.link = master
        assert follower.is_linked

        state = SessionState(fits=[])
        result = parameter_unlink(
            state, parameter_uid=follower.unique_identifier,
        )
        assert result["ok"]
        assert not follower.is_linked

    def test_link_unknown_target_uid(self):
        g = _group(["f"])
        follower = g.parameters_all_dict["f"]
        state = SessionState(fits=[])
        result = parameter_link(
            state,
            parameter_uid=follower.unique_identifier,
            target_parameter_uid="nope",
        )
        assert not result["ok"]
