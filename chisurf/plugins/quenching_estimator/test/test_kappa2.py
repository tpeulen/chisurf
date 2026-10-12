"""κ² is stated, not modelled — and stating it must change nothing by default.

OBJ-01 item 6 asked for an orientation factor. It cannot be *computed* here:
QuEst's dye is a structureless point diffusing in an accessible volume, with no
transition dipole to orient. `IMP.bff.cgdye.rotamer.scoring.kappa2_from_vectors`
does compute it, and takes the two dipole vectors — precisely what QuEst has
not got. So the item closes as **chosen and documented**, not as modelled, and
these tests hold that distinction in place:

* the default is the isotropic dynamic average 2/3, which a published Förster
  radius already assumes, so every number computed before `fret.kappa2` existed
  is reproduced exactly;
* the value reaches the transfer rate, with the literature's ``1.5 · κ²``;
* an unphysical value is refused when the project is read, not eight frames
  into a run.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core.av import (
    ISOTROPIC_KAPPA2,
    MAX_KAPPA2,
    _kappa2_scale,
    fret_rate_pair_trace,
    fret_rate_trace,
)


def _pair(n_frames: int = 64, separation: float = 40.0):
    donor = np.zeros((n_frames, 3))
    acceptor = np.tile(np.array([separation, 0.0, 0.0]), (n_frames, 1))
    return donor, acceptor


class TestTheScaleFactor:
    def test_the_isotropic_average_is_neutral(self) -> None:
        assert _kappa2_scale(ISOTROPIC_KAPPA2) == pytest.approx(1.0)
        assert _kappa2_scale(None) == pytest.approx(1.0)

    def test_it_is_the_literature_factor(self) -> None:
        """``κ²/(2/3)`` is the ``1.5 κ²`` that appears in published rates."""
        for kappa2 in (0.0, 0.25, 2.0 / 3.0, 1.0, 4.0):
            assert _kappa2_scale(kappa2) == pytest.approx(1.5 * kappa2)

    @pytest.mark.parametrize("bad", [-0.1, MAX_KAPPA2 + 0.1, float("nan"), float("inf")])
    def test_an_unphysical_value_is_refused(self, bad: float) -> None:
        with pytest.raises(ValueError, match="kappa2"):
            _kappa2_scale(bad)


class TestItReachesTheRate:
    def test_the_default_reproduces_the_rate_exactly(self) -> None:
        donor, acceptor = _pair()
        without = fret_rate_pair_trace(donor, acceptor, R0=52.0, tau0=4.0)
        stated = fret_rate_pair_trace(
            donor, acceptor, R0=52.0, tau0=4.0, kappa2=ISOTROPIC_KAPPA2
        )
        assert np.array_equal(without, stated)

    def test_the_rate_is_linear_in_kappa2(self) -> None:
        donor, acceptor = _pair()
        base = fret_rate_pair_trace(
            donor, acceptor, R0=52.0, tau0=4.0, kappa2=ISOTROPIC_KAPPA2
        )
        doubled = fret_rate_pair_trace(
            donor, acceptor, R0=52.0, tau0=4.0, kappa2=2 * ISOTROPIC_KAPPA2
        )
        assert doubled == pytest.approx(2.0 * base)

    def test_perpendicular_dipoles_transfer_nothing(self) -> None:
        donor, acceptor = _pair()
        rates = fret_rate_pair_trace(donor, acceptor, R0=52.0, tau0=4.0, kappa2=0.0)
        assert np.all(rates == 0.0)

    def test_the_averaged_regime_takes_it_too(self) -> None:
        """The fast-acceptor limit must not quietly ignore the parameter."""
        trajectory = np.zeros((32, 3))
        points = np.tile(np.array([40.0, 0.0, 0.0]), (16, 1))
        base = fret_rate_trace(trajectory, points, R0=52.0, tau0=4.0)
        doubled = fret_rate_trace(
            trajectory, points, R0=52.0, tau0=4.0, kappa2=2 * ISOTROPIC_KAPPA2
        )
        assert doubled == pytest.approx(2.0 * base)


class TestTheProjectCarriesIt:
    def test_the_template_states_the_assumption(self) -> None:
        from chisurf.plugins.quenching_estimator.core.project import template_project

        project = template_project(with_fret=True)
        assert project["fret"]["kappa2"] == pytest.approx(ISOTROPIC_KAPPA2)

    def test_a_bad_value_is_a_malformed_project(self) -> None:
        """Refused by the validator, before a structure is even resolved.

        kappa2 = 9 would otherwise multiply the transfer rate by 13.5 and
        surface only as an implausible efficiency.
        """
        from pathlib import Path

        from chisurf.plugins.quenching_estimator.core.project import ProjectValidationError, template_project, validate_project

        project = template_project(with_fret=True)
        project["pdb"] = str(Path(__file__).parent / "148l.pdb")
        project["fret"]["kappa2"] = 9.0
        with pytest.raises(ProjectValidationError, match="kappa2"):
            validate_project(project)

    def test_the_catalog_documents_it_in_every_language(self) -> None:
        from chisurf.plugins.quenching_estimator.core import i18n

        for locale in i18n.available_locales():
            catalog = i18n.translate_catalog(locale)
            entry = catalog["parameters"]["fret.kappa2"]
            assert entry["label"].strip()
            assert entry["description"].strip()

    def test_the_model_defaults_to_isotropic(self) -> None:
        from chisurf.plugins.quenching_estimator.core.dye_diffusion import DonorDecay

        assert DonorDecay().fret_kappa2 == pytest.approx(ISOTROPIC_KAPPA2)
