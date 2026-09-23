"""Edits and links to any parameter of the session, over the fitting client.

A table or a network that shows every parameter of every fit and plugin group
changes them through this, never by assignment: fit parameters are addressed by
their fit (``fit_uid``/``fit_index``, a group's ``local_idx``) and name, which
is the path the server has always taken; out-of-fit parameters by their global
``parameter_uid``, which the server resolves through its identifier index.

Rows are :class:`~chisurf.core.fitting.parameter_network.ParameterRow`. Every
method answers the RPC's ``{"ok": ...}`` and ``{"ok": False}`` when there is no
fitting client.
"""

from __future__ import annotations

from typing import Any

from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client

__all__ = ["FittingClientParamMutator"]


class FittingClientParamMutator:
    """Route parameter edits and links through the :class:`FittingClient`."""

    @staticmethod
    def address(row: Any) -> dict:
        """The RPC keywords that address *row*'s parameter."""
        if row.kind == "fit":
            return {
                "parameter_name": str(getattr(row.param, "name", "")),
                "fit_uid": row.fit_uid or None,
                "fit_index": row.fit_index,
                "local_idx": row.local_idx,
            }
        return {
            "parameter_name": str(getattr(row.param, "name", "")),
            "parameter_uid": row.param_uid,
            "owner_uid": row.owner_uid,
        }

    def set_value(self, row, value):
        """Set a parameter's value."""
        fc = get_fitting_client()
        return fc.set_parameter_value(value=value, **self.address(row)) if fc else {"ok": False}

    def set_fixed(self, row, fixed):
        """Hold a parameter, or free it."""
        fc = get_fitting_client()
        return fc.set_parameter_fixed(fixed=fixed, **self.address(row)) if fc else {"ok": False}

    def set_bounds(self, row, bounds):
        """Set a parameter's ``(lo, hi)``."""
        fc = get_fitting_client()
        return fc.set_parameter_bounds(bounds=bounds, **self.address(row)) if fc else {"ok": False}

    def set_bounds_on(self, row, bounds_on):
        """Switch a parameter's bounds on or off."""
        fc = get_fitting_client()
        if fc is None:
            return {"ok": False}
        return fc.set_parameter_bounds_on(bounds_on=bounds_on, **self.address(row))

    def link(self, src, target):
        """Make *src* follow *target*."""
        fc = get_fitting_client()
        if fc is None:
            return {"ok": False}
        kw = self.address(src)
        # The master is addressed by its global uid, whatever owns it.
        kw["target_parameter_name"] = str(getattr(target.param, "name", ""))
        kw["target_parameter_uid"] = target.param_uid
        return fc.link_parameters(**kw)

    def unlink(self, row):
        """Break *row*'s link."""
        fc = get_fitting_client()
        return fc.unlink_parameter(**self.address(row)) if fc else {"ok": False}
