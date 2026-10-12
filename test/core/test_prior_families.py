"""The smooth-prior catalogue both shells' Prior selectors share (Qt-free)."""

from __future__ import annotations

import math

import pytest

from chisurf.core.fitting import prior_families as pf
from chisurf.core.fitting.priors import prior_from_state


def test_every_family_builds_a_prior_from_its_seeded_state():
    for _label, kind, _params in pf.PRIOR_FAMILY_SPECS:
        state = pf.seeded_prior_state(kind, 4.0)
        assert state["kind"] == kind
        assert prior_from_state(state) is not None, kind


def test_a_width_is_a_tenth_of_the_value_and_a_lognormal_centres_on_its_log():
    assert pf.seeded_prior_state("normal", 5.0) == {"kind": "normal", "mu": 5.0, "sigma": 0.5}
    assert pf.seeded_prior_state("lognormal", math.e)["mu"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Gaussian(4, 0.4)", {"kind": "normal", "mu": 4.0, "sigma": 0.4}),
        ("gaussian", {"kind": "normal", "mu": 5.0, "sigma": 0.5}),
        ("half_normal(2, 1)", {"kind": "half_normal", "sigma": 2.0, "loc": 1.0}),
        ("Box", None),
        ("", None),
    ],
)
def test_typed_priors_parse(text, expected):
    ok, state = pf.parse(text, 5.0)
    assert ok and state == expected


def test_text_naming_no_family_is_refused():
    assert pf.parse("Cauchy", 1.0) == (False, None)


def test_describe_is_what_parse_reads_back():
    state = pf.parse("Truncated Gaussian(1, 2, 0, 5)", 3.0)[1]
    assert pf.describe(state) == "Truncated Gaussian(1, 2, 0, 5)"
    assert pf.parse(pf.describe(state), 3.0)[1] == state
    assert pf.describe(None) == "Box" and pf.describe({"kind": "uniform"}) == "Box"
