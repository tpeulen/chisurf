"""Route a ChiSurf fit at a model family BFF ships as a description.

This module decides nothing about topology, and that is the whole point of it.
Which structures exist, how the search moves between them, how candidates are
scored and how each is fitted all live in BFF, in a JSON description BFF owns.
What stays here is what only the application can know: the user's data and
instrument, which of their parameters are fixed or linked, and how the answer
is written back onto the model they configured.

It replaces a Python declaration of the same lattice. That declaration was a
second copy of a topology BFF now ships as a file, and a second copy is two
opinions about what a lifetime family is.

A fit BFF cannot represent completely is refused, not approximated. The
description reproduces ChiSurf's configured decay bit for bit -- verified
against the node ChiSurf itself builds -- but only for the terms it carries,
so every term it does not carry is a refusal below.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from chisurf.core.fitting.mcts.native import (
    NativeSearchPreparation,
    NativeSearchReason,
    _restore,
    _snapshot,
    unsupported,
)

CAPABILITY_ID = "chisurf.tcspc.lifetime.description.v1"
FAMILY = "tcspc_lifetime"


def _owner(parameter: Any) -> Any | None:
    """The terminal owner of a link chain, or None on a cycle."""
    seen: set[int] = set()
    current = parameter
    while getattr(current, "is_linked", False):
        if id(current) in seen:
            return None
        seen.add(id(current))
        current = getattr(current, "link", None)
        if current is None:
            return None
    return current


def _refuse_unrepresentable(fit: Any, model: Any) -> NativeSearchPreparation | None:
    """Every term the description does not carry is a refusal, not a guess.

    These mirror the refusals ChiSurf's own graph builder makes, because the
    description is only equivalent to that builder where both carry a term.
    """
    from chisurf.core.models.tcspc.lifetime import LifetimeModel

    if type(model) is not LifetimeModel:
        return unsupported(
            CAPABILITY_ID, "unsupported_model_family",
            "this description covers plain TCSPC LifetimeModel fits")
    convolve, generic, lifetimes = model.convolve, model.generic, model.lifetimes
    reasons = (
        (getattr(convolve, "mode", None) != "per",
         "non_periodic_convolution", "the description reconvolves periodically only"),
        (not getattr(convolve, "do_convolution", False),
         "no_convolution", "an unconvolved decay is a different curve"),
        (generic.background_curve is not None,
         "measured_background_curve", "a measured background is a second curve"),
        (getattr(lifetimes, "_link", None) is not None,
         "linked_spectrum", "the spectrum comes from another model"),
        (getattr(lifetimes, "_lifetime_spectrum", None) is not None,
         "fixed_spectrum", "a spectrum set outright is not searchable"),
    )
    for failed, code, message in reasons:
        if failed:
            return unsupported(CAPABILITY_ID, code, message)
    anisotropy = getattr(model, "anisotropy", None)
    if anisotropy is not None and not anisotropy._is_vm_polarization(
        anisotropy.polarization_type
    ):
        # Polarised TCSPC is its own family, tcspc_anisotropy, whose channels
        # are fitted together; one polarised curve is not that family.
        return unsupported(
            CAPABILITY_ID, "polarised_decay",
            "a polarised decay belongs to the joint anisotropy family")
    return None


def _structural_owners(
    model: Any,
) -> list[tuple[Any, Any]] | NativeSearchPreparation:
    """One independent (amplitude, lifetime) owner pair per allocated row."""
    rows = list(zip(model.lifetimes._amplitudes, model.lifetimes._lifetimes))
    if not rows:
        return unsupported(CAPABILITY_ID, "empty_structure", "the model has no lifetime row")
    claimed: set[int] = set()
    owners: list[tuple[Any, Any]] = []
    for index, (amplitude, lifetime) in enumerate(rows):
        pair = []
        for parameter in (amplitude, lifetime):
            owner = _owner(parameter)
            if owner is None:
                return unsupported(
                    CAPABILITY_ID, "cyclic_structural_link",
                    f"structural parameter {parameter.name!r} has no terminal link owner",
                    str(parameter.name))
            if id(owner) in claimed:
                return unsupported(
                    CAPABILITY_ID, "coupled_structural_rows",
                    f"canonical owner {owner.name!r} controls more than one structural row",
                    str(owner.name))
            # The first amplitude pins the scale under normalisation and is
            # never released by the search, so a user fixing it costs nothing.
            releasable = not (index == 0 and parameter is amplitude)
            if releasable and bool(getattr(owner, "fixed", False)):
                return unsupported(
                    CAPABILITY_ID, "fixed_structural_parameter",
                    f"user-fixed structural parameter {owner.name!r} will not be released",
                    str(owner.name))
            claimed.add(id(owner))
            pair.append(owner)
        owners.append((pair[0], pair[1]))
    return owners


def _measurement(values: Any, errors: Any = None) -> Any:
    """ChiSurf data as a bff measurement; errors travel as a stored variance."""
    import IMP.bff as bff

    dataset = bff.FitDataset()
    dataset.set_values_array(np.ascontiguousarray(np.asarray(values, dtype=float)))
    if errors is not None:
        dataset.set_noise_family(bff.FIT_NOISE_FAMILY_STORED)
        dataset.set_stored_variance_array(
            np.ascontiguousarray(np.asarray(errors, dtype=float) ** 2))
    return dataset


@dataclass
class DescriptionBinding:
    """What interpreting a cached BFF state back onto the model needs."""

    fit: Any
    model: Any
    rows: list[tuple[Any, Any]]
    instrument: dict[str, Any]
    live_parameters: tuple[Any, ...]

    def apply_state(self, problem: Any, state: Any) -> None:
        """Write one winning state onto the user's model as one transaction."""
        ids = list(problem.get_parameter_ids())
        values = dict(zip(ids, problem.get_cached_values(state.get_key())))
        fixed = dict(zip(ids, problem.get_cached_fixed(state.get_key())))
        snapshot = _snapshot(self.live_parameters)
        try:
            for index, (amplitude, lifetime) in enumerate(self.rows):
                tau_id = f"lifetime.tau.{index}"
                active = tau_id in fixed and not fixed[tau_id]
                if active:
                    lifetime.fixed = False
                    lifetime.value = float(values[tau_id])
                    if index > 0:
                        amplitude.fixed = False
                        amplitude.value = float(values[f"lifetime.amplitude.{index}"])
                else:
                    # A row the winner does not use contributes nothing. BFF
                    # holds a seed amplitude there; writing it would add a
                    # component to the user's model that was never fitted.
                    amplitude.value = 0.0
                    amplitude.fixed = True
                    lifetime.fixed = True
            for canonical, parameter in self.instrument.items():
                # The user's fixed/free choice is theirs; only the value moves.
                if canonical in values and not bool(getattr(parameter, "fixed", False)):
                    parameter.value = float(values[canonical])
            self.model.find_parameters()
            self.model.update()
            update = getattr(self.fit, "update", None)
            if callable(update):
                update()
        except Exception:
            _restore(snapshot)
            self.model.find_parameters()
            raise


def prepare_lifetime_description_search(fit: Any) -> NativeSearchPreparation:
    """Build BFF's lifetime search for a fit, or say precisely why not."""
    import IMP.bff as bff

    model = getattr(fit, "model", None)
    if model is None:
        return unsupported(CAPABILITY_ID, "missing_fitting_model",
                           "the selected object does not expose a fitting model")
    refusal = _refuse_unrepresentable(fit, model)
    if refusal is not None:
        return refusal
    model.find_parameters()
    rows = _structural_owners(model)
    if isinstance(rows, NativeSearchPreparation):
        return rows

    convolve, generic, corrections = model.convolve, model.generic, model.corrections
    data = fit.data
    y = np.ascontiguousarray(data.y, dtype=float)
    ey = np.ascontiguousarray(data.ey, dtype=float)
    if y.size == 0 or ey.size != y.size:
        return unsupported(CAPABILITY_ID, "incomplete_data", "the fit has no usable data")
    try:
        response = np.ascontiguousarray(convolve._process_irf(normalize=True).y, dtype=float)
    except Exception as error:  # an instrument without a response
        return unsupported(CAPABILITY_ID, "no_response", f"no usable response: {error}")
    if response.size != y.size:
        return unsupported(CAPABILITY_ID, "response_length",
                           "the response and the decay differ in length")

    # The component ceiling is the rows the user allocated; the lattice over
    # them is the description's, read from the file BFF ships.
    document = json.loads(open(bff.get_data_path(f"model_search/{FAMILY}.json")).read())
    document["axes"]["n"]["to"] = len(rows)
    spec = bff.ModelSearchSpec.from_json(json.dumps(document))
    spec.set_dataset("decay", _measurement(y, ey))
    spec.set_dataset("response", _measurement(response))
    spec.set_scalar("dt", float(convolve.dt))
    spec.set_scalar("period", 1000.0 / float(convolve.rep_rate))
    spec.set_scalar("convolution_stop", float(int(convolve.stop)))
    spec.set_scalar("scale_stop", float(min(int(convolve.stop), y.size)))
    # ChiSurf spells "autoscale" as a fixed n0.
    spec.set_scalar("autoscale", 1.0 if bool(convolve._n0.fixed) else 0.0)
    if getattr(corrections, "correct_pile_up", False):
        spec.set_scalar("pile_up", 1.0)
        spec.set_scalar("dead_time", float(corrections.dead_time))
        spec.set_scalar("measurement_time", float(corrections.measurement_time))
    if getattr(corrections, "correct_dnl", False):
        table = np.asarray(corrections.lintable, dtype=float)
        if table.ndim != 1 or table.size != y.size:
            return unsupported(CAPABILITY_ID, "linearization_length",
                               "the DNL table does not match the decay")
        spec.set_dataset("linearization", _measurement(table))

    # The user's own lifetime rows reach BFF as starting values. This is not
    # a convenience: the first amplitude is fixed under normalisation and
    # every other amplitude is fitted as a ratio to it, so a search started
    # from BFF's neutral seed would return fractions relative to a different
    # reference than the model the answer is written back onto. Freedom stays
    # the description's to decide per structure.
    for index, (amplitude, lifetime) in enumerate(rows):
        spec.set_parameter_value(f"lifetime.amplitude.{index}", float(amplitude.value), True)
        spec.set_parameter_value(f"lifetime.tau.{index}", float(lifetime.value), True)

    instrument = {
        "instrument.n0": convolve._n0,
        "instrument.background": generic._bg,
        "instrument.scatter": generic._sc,
        "instrument.timeshift": convolve._ts,
    }
    # Every value and every fixed/free choice the user made reaches BFF as a
    # caller override, which BFF ranks above its own description.
    for canonical, parameter in instrument.items():
        owner = _owner(parameter)
        if owner is None:
            return unsupported(CAPABILITY_ID, "cyclic_link",
                               f"{parameter.name!r} has no terminal link owner")
        value = float(owner.value)
        free = not bool(getattr(owner, "fixed", False))
        lower, upper = getattr(owner, "bounds", (None, None))
        if (getattr(owner, "bounds_on", False) and lower is not None
                and upper is not None and float(upper) > float(lower)):
            # The user bounded it, so their bounds stand -- including a lower
            # bound of zero, which a truthiness test would have discarded.
            spec.set_parameter(canonical, value, free, float(lower), float(upper))
        else:
            # No bounds of the user's own: keep the description's, which are
            # derived from the data. Inventing wide ones would change the fit.
            spec.set_parameter_value(canonical, value, free)

    try:
        problem = spec.build()
    except Exception as error:
        return unsupported(CAPABILITY_ID, "description_refused", str(error))

    live = tuple(model.parameters_all) + tuple(p for row in rows for p in row) \
        + tuple(instrument.values())
    binding = DescriptionBinding(fit, model, rows, instrument, live)
    return NativeSearchPreparation(CAPABILITY_ID, problem=problem, binding=binding)


__all__ = ["CAPABILITY_ID", "FAMILY", "DescriptionBinding",
           "prepare_lifetime_description_search"]
