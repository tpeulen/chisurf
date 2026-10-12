"""The fit report (the *Info* tab) lists what the fit computes with, once per fit.

A catalogue model (``Parse-Model``) holds the parameters of every equation of its
catalogue; the report listed all of them -- six live parameters under a hundred
fixed ones of equations nobody chose. A global fit's report keyed its local fits'
parameters by bare name, so the ``N`` of three curves collapsed into one row
holding whichever curve came last.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("IMP.bff")

import chisurf.core.data
import chisurf.core.fitting.fit as F
from chisurf.core.models.fcs.parse import ParseFCSModel
from chisurf.core.models.global_model.globalfit import GlobalFitModel

EQUATION = "3D Gauss, 1 bunching"
LIVE = {"b", "N", "td", "s", "ba", "bt"}


def _fcs_fit(name: str, td: float = 0.03):
    x = np.logspace(-3, 2, 60)
    y = 1.0 + 0.2 / (1.0 + x / td)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(x, 0.01))
    fit = F.Fit(model_class=ParseFCSModel, data=data)
    fit.xmin, fit.xmax = 0, x.size
    fit.name = name
    fit.model.structure = EQUATION
    return fit


def _names(report: str) -> list:
    """The names of the report's parameter table (after its header, up to the next blank line)."""
    names = []
    for line in report.split("\n\n", 1)[1].splitlines()[1:]:
        if not line.strip():
            break
        names.append(line.split()[0])
    return names


def test_a_catalogue_model_reports_only_the_active_equation():
    fit = _fcs_fit("one")
    assert len(fit.model.parameters_all) > len(LIVE)  # the catalogue's other equations are held
    assert set(name for name, _ in F.reported_parameters(fit.model)) == LIVE
    assert set(_names(str(fit))) == LIVE
    assert {entry["name"] for entry in fit.prior_summary()} <= LIVE  # the "bounds only" line too


def test_a_global_fit_reports_every_local_fit_separately():
    members = [_fcs_fit(f"curve {i}") for i in (1, 2, 3)]
    for value, member in zip((4.0, 5.0, 6.0), members):
        member.model.parameters_all_dict["N"].value = value
    data = chisurf.core.data.DataCurve(x=np.arange(2.0), y=np.zeros(2))
    group = F.Fit(model_class=GlobalFitModel, data=data)
    for member in members:
        group.model.append_fit(member)
    rows = dict(F.reported_parameters(group.model))
    assert [rows[f"{i}:N"].value for i in (1, 2, 3)] == [4.0, 5.0, 6.0]
    assert not any(name.split(":", 1)[-1] not in LIVE for name in rows if ":" in name)
    assert {f"{i}:N" for i in (1, 2, 3)} <= set(_names(str(group)))


def test_a_global_run_refreshes_the_chi2_its_local_fits_list():
    """A local fit listed the chi2r of its own last run after a global fit had moved it (0.677 beside 0.709)."""
    members = [_fcs_fit("fast", 0.02), _fcs_fit("slow", 0.06)]
    for member in members:
        member.run()
    data = chisurf.core.data.DataCurve(x=np.arange(2.0), y=np.zeros(2))
    group = F.Fit(model_class=GlobalFitModel, data=data)
    for member in members:
        group.model.append_fit(member)
    # one diffusion time for both curves: the joint optimum is neither curve's own
    members[1].model.parameters_all_dict["td"].link = members[0].model.parameters_all_dict["td"]
    before = [member.__dict__["_last_chi2r"] for member in members]
    group.run()
    after = [float(member.chi2r) for member in members]
    assert after[1] > 2 * before[1]  # the global run did move the slow curve off its own optimum
    for member, value in zip(members, after):
        assert member.__dict__["_last_chi2r"] == pytest.approx(value, rel=1e-6)
