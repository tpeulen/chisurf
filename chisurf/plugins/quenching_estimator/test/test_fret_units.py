"""Every length in a QuEst project is in Angstrom — R0 included.

The existing FRET tests assert only ``0 <= E <= 1``, which is true of *any*
number the model can produce, so they stayed green while the shipped template
carried a Förster radius of 5.5 (a nanometre value). At realistic
donor-acceptor distances that is a transfer rate of order 1e-6: FRET silently
switched off. These cases pin the unit instead of the range.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chisurf.plugins.quenching_estimator.core import build_donor_from_project
from chisurf.plugins.quenching_estimator.core.project import DEFAULT_FORSTER_RADIUS, template_project


def _efficiency(r_da: float, r0: float) -> float:
    """The Förster relation the simulation uses, for reference values."""
    return 1.0 / (1.0 + (r_da / r0) ** 6)


class TestTemplateForsterRadius:
    def test_template_r0_is_a_plausible_forster_radius_in_angstrom(self) -> None:
        matrix = template_project(with_fret=True)["fret"]["R0_matrix"]
        r0 = matrix[0][1]
        assert r0 == DEFAULT_FORSTER_RADIUS
        # Real donor-acceptor pairs sit in this band in Angstrom. A nanometre
        # value (~5) or a metre-ish one would fall outside it.
        assert 20.0 <= r0 <= 80.0, f"R0={r0} is not a Forster radius in Angstrom"

    def test_r0_matrix_is_symmetric_with_an_empty_diagonal(self) -> None:
        matrix = template_project(with_fret=True)["fret"]["R0_matrix"]
        assert matrix[0][0] is None and matrix[1][1] is None
        assert matrix[0][1] == matrix[1][0]

    def test_no_r0_matrix_without_an_acceptor(self) -> None:
        assert "R0_matrix" not in template_project(with_fret=False)["fret"]

    def test_the_donor_picks_up_r0_from_the_matrix(self) -> None:
        project = template_project(with_fret=True)
        project["pdb"] = str(Path(__file__).parent / "148l.pdb")

        donor = build_donor_from_project(project)
        assert donor.fret_R0 == DEFAULT_FORSTER_RADIUS

    def test_the_template_radius_gives_measurable_transfer(self) -> None:
        """The failure this guards: a too-small R0 makes E vanish, not error."""
        r0 = DEFAULT_FORSTER_RADIUS
        # Around R0 the pair is half-transferring; the template must land there
        # for a typical labelled protein, not at zero.
        assert _efficiency(r0, r0) == pytest.approx(0.5)
        assert _efficiency(40.0, r0) > 0.5
        assert _efficiency(80.0, r0) > 1e-2
        # ... whereas a nanometre value is indistinguishable from no acceptor.
        assert _efficiency(40.0, 5.5) < 1e-4
