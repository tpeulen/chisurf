"""Three-colour PDA: the swapped-label mirrors are not states of their own.

The stochastic-labelling correction accompanies every distance population with
a mirror in which the green and red labels sit on the other site. A molecule
keeps its labels for its lifetime, so a transition is a change of
*conformation*, never of labelling — the mirrors exchange among themselves.

Reading the flat species list positionally breaks that: ``species[:2]`` used to
pick population one **and its own mirror image** as "the two exchanging states"
and hand the real second state to the static branch, and the multistate route
saw twice as many species as its rate matrix has rows. These tests pin the
per-labelling-configuration evaluation that fixes both (RF-148).
"""

import numpy as np
import pytest

WINDOW = 2e-3
LABELING = 0.8

#: (R_GR, R_BG, R_BR) of the two populations the tests exchange between.
STATES = ((45.0, 42.0, 58.0), (70.0, 64.0, 82.0))


def _model(states=STATES, n_bursts=150, seed=3, labeling: float = 1.0):
    """Return a two-population PDA3c model with the given distances.

    Parameters
    ----------
    states : sequence of tuple
        ``(R_GR, R_BG, R_BR)`` per population.
    n_bursts : int
        Bursts drawn by the simulator reader.
    seed : int
        Simulator seed, so every model in a test sees the same bursts.
    labeling : float
        ``F(labeling)``; below one the correction is switched on as well.

    Returns
    -------
    chisurf.core.models.pda3c.pda3c.Pda3cModel
    """
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.experiments.pda3c import Pda3cSimulatorReader
    from chisurf.core.models.pda3c.pda3c import Pda3cModel

    data = Pda3cSimulatorReader(n_bursts=n_bursts, seed=seed).read()[0]
    model = fit_mod.Fit(model_class=Pda3cModel, data=data).model
    while len(model.species) < len(states):
        model.species.append()
    for index, (r_gr, r_bg, r_br) in enumerate(states):
        for parameter, value in zip(model.species.means_of(index), (r_gr, r_bg, r_br)):
            parameter.value = value
        model.species._amplitudes[index].value = 1.0
    model.setup._window.value = WINDOW
    if labeling < 1.0:
        model.stochastic_labeling = True
        model.setup._labeling_fraction.value = labeling
    model.find_parameters()
    return model


def _mirror(states):
    """Return the label-swapped distances: ``R_BG`` and ``R_BR`` trade places."""
    return tuple((r_gr, r_br, r_bg) for r_gr, r_bg, r_br in states)


def _per_burst(model):
    """Return the model's per-burst log likelihood."""
    return model._per_burst_log_likelihood(model.burst_counts())


def _labeling_mixture(intended, swapped, fraction: float = LABELING):
    """Combine the two labelling configurations' per-burst likelihoods."""
    from scipy.special import logsumexp

    return logsumexp(
        np.log([fraction, 1.0 - fraction])[:, None] + np.stack([intended, swapped]),
        axis=0,
    )


# -- the two-state K_ex route ------------------------------------------------


def test_the_exchanging_pair_is_two_populations_not_a_population_and_its_mirror():
    """The labelled dynamic model is the mixture of two dynamic models.

    One per labelling configuration, weighted by ``F(labeling)`` — an exact
    identity, not an approximation, because labelling and conformation are
    independent and labelling does not change during a burst. The positional
    slice of the flat list satisfies no such identity: it exchanges population
    one with its own mirror while population two stays static.
    """
    labelled = _model(labeling=LABELING)
    labelled.dynamic = True
    labelled.setup._k_ex.value = 3.0

    pieces = []
    for states in (STATES, _mirror(STATES)):
        model = _model(states=states)
        model.dynamic = True
        model.setup._k_ex.value = 3.0
        pieces.append(_per_burst(model))

    assert _per_burst(labelled) == pytest.approx(_labeling_mixture(*pieces), rel=1e-9)


def test_the_mirror_pair_is_not_what_exchanges():
    """The fixed model must disagree with the old positional slice.

    Without this the identity above could be satisfied by a route that happens
    to be numerically indistinguishable from the defect — it is not: the
    likelihood moves by hundreds of units.
    """
    labelled = _model(labeling=LABELING)
    labelled.dynamic = True
    labelled.setup._k_ex.value = 3.0
    counts = labelled.burst_counts()
    setup = labelled.setup.as_setup()

    flat = labelled.species.as_species(labelled._labeling_weight())
    positional = labelled._two_state_mixture_log_likelihood(counts, flat, setup)

    assert float(np.sum(positional)) != pytest.approx(float(np.sum(_per_burst(labelled))), rel=1e-3)


def test_one_population_with_a_mirror_is_not_a_two_state_exchange():
    """A single population is static however many mirrors the correction adds."""
    labelled = _model(states=STATES[:1], labeling=LABELING)
    labelled.dynamic = True
    labelled.setup._k_ex.value = 3.0
    static = _model(states=STATES[:1], labeling=LABELING)

    assert _per_burst(labelled) == pytest.approx(_per_burst(static), rel=1e-12)


# -- the multistate route ----------------------------------------------------


def test_the_rate_matrix_is_sized_by_the_populations_not_the_components():
    """A 2x2 scheme fits two populations even with the correction on.

    It used to raise ``ValueError`` — the flat list held four components — which
    a swallowed exception then turned into an empty residual.
    """
    labelled = _model(labeling=LABELING)
    labelled.dynamic = True
    labelled.rate_matrix = np.array([[0.0, 400.0], [300.0, 0.0]])

    assert labelled.rate_matrix.shape == (2, 2)
    assert np.all(np.isfinite(_per_burst(labelled)))


def test_the_multistate_route_mixes_the_labelling_configurations():
    """Same identity as the two-state route, for the sampled multistate one."""
    scheme = np.array([[0.0, 400.0], [300.0, 0.0]])
    labelled = _model(labeling=LABELING)
    labelled.dynamic = True
    labelled.rate_matrix = scheme

    pieces = []
    for states in (STATES, _mirror(STATES)):
        model = _model(states=states)
        model.dynamic = True
        model.rate_matrix = scheme
        pieces.append(_per_burst(model))

    assert _per_burst(labelled) == pytest.approx(_labeling_mixture(*pieces), rel=1e-9)


# -- what the split returns --------------------------------------------------


def test_labeling_variants_are_states_in_population_order():
    """One entry per configuration, each holding one component per population."""
    species = _model(labeling=LABELING).species
    variants = species.as_labeling_variants(LABELING)

    assert [weight for weight, _ in variants] == pytest.approx([LABELING, 1.0 - LABELING])
    for _, states in variants:
        assert len(states) == len(STATES)
    intended, swapped = (states for _, states in variants)
    for state, mirror, (r_gr, r_bg, r_br) in zip(intended, swapped, STATES):
        assert state.means == pytest.approx([r_gr, r_bg, r_br])
        assert mirror.means == pytest.approx([r_gr, r_br, r_bg])
        assert state.amplitude == pytest.approx(mirror.amplitude)


def test_a_full_labelling_has_one_configuration():
    """With the correction off nothing is expanded, so nothing costs more."""
    species = _model().species
    variants = species.as_labeling_variants(1.0)

    assert len(variants) == 1
    assert variants[0][0] == pytest.approx(1.0)
    assert len(variants[0][1]) == len(STATES)


def test_the_flat_mixture_still_interleaves_the_mirrors():
    """``as_species`` is unchanged — the static routes read it as a mixture."""
    species = _model(labeling=LABELING).species
    flat = species.as_species(LABELING)

    assert len(flat) == 2 * len(STATES)
    assert flat[0].means == pytest.approx(list(STATES[0]))
    assert flat[1].means == pytest.approx([STATES[0][0], STATES[0][2], STATES[0][1]])
    assert flat[0].amplitude == pytest.approx(LABELING)
    assert flat[1].amplitude == pytest.approx(1.0 - LABELING)
