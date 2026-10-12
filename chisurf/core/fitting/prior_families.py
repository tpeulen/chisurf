"""The smooth-prior families a parameter's *Prior* selector offers, Qt-free.

Both shells (the Qt parameter popup and the emtk parameter tables) read the same catalogue:
a display label, the prior ``kind`` of :mod:`chisurf.core.fitting.priors` and the editable
shape parameters ``(key, label, default)``. *Box* is the degenerate uniform prior -- the plain
lower/upper bounds -- and is not a family: choosing it clears the smooth prior.
"""

from __future__ import annotations

import math
import re
from typing import Any

#: Display label, prior ``kind`` and ``(key, label, default)`` per shape parameter.
PRIOR_FAMILY_SPECS = [
    ("Gaussian", "normal", [("mu", "Mean μ", 0.0), ("sigma", "Std σ", 1.0)]),
    (
        "Truncated Gaussian",
        "truncated_normal",
        [
            ("mu", "Mean μ", 0.0),
            ("sigma", "Std σ", 1.0),
            ("lb", "Lower", 0.0),
            ("ub", "Upper", 1.0),
        ],
    ),
    ("Log-normal", "lognormal", [("mu", "Mean of ln x", 0.0), ("sigma", "Std of ln x", 0.5)]),
    ("Half-normal", "half_normal", [("sigma", "Std σ", 1.0), ("loc", "Edge", 0.0)]),
    ("Exponential", "exponential", [("scale", "Mean scale", 1.0), ("loc", "Edge", 0.0)]),
    ("Gamma", "gamma", [("alpha", "Shape α", 2.0), ("beta", "Rate β", 1.0), ("loc", "Edge", 0.0)]),
    ("Beta", "beta", [("alpha", "Shape α", 2.0), ("beta", "Shape β", 2.0)]),
]
PRIOR_KIND_TO_SPEC = {kind: (label, params) for (label, kind, params) in PRIOR_FAMILY_SPECS}

#: The selector's entry for the uniform/box prior: "no smooth prior, just bounds".
PRIOR_KIND_BOX = "box"
#: Label of the Box entry.
BOX_LABEL = "Box (bounds only)"


def seeded_prior_state(kind: str, seed: float) -> dict:
    """Default state of family *kind*, with location parameters at the current value *seed*.

    A width defaults to a tenth of the parameter's magnitude rather than to a flat 1.0: a prior
    on a rate of 1e-3 and one on a lifetime of 4 ns need very different scales.

    Parameters
    ----------
    kind : str
        A ``kind`` of :data:`PRIOR_FAMILY_SPECS`.
    seed : float
        The parameter's current value.
    """
    try:
        seed = float(seed)
    except (TypeError, ValueError):
        seed = 1.0
    if not math.isfinite(seed):
        seed = 1.0
    scaled_sigma = abs(seed) * 0.1
    _, params = PRIOR_KIND_TO_SPEC[kind]
    state: dict[str, Any] = {"kind": kind}
    for key, _label, default in params:
        value = default
        if key in ("mu", "loc") and kind != "lognormal":
            value = seed
        elif key == "mu" and kind == "lognormal" and seed > 0:
            value = math.log(seed)
        elif key == "sigma" and kind != "lognormal" and scaled_sigma > 0:
            value = scaled_sigma
        state[key] = value
    return state


def family_label(state: dict | None) -> str:
    """The selector's label for a prior state (``Box (bounds only)`` for none or uniform)."""
    kind = (state or {}).get("kind")
    if kind in PRIOR_KIND_TO_SPEC:
        return PRIOR_KIND_TO_SPEC[kind][0]
    return "" if (kind and kind != "uniform") else BOX_LABEL


def describe(state: dict | None) -> str:
    """A prior state as the table shows and accepts it: ``Gaussian(4, 0.4)``; ``Box`` for none."""
    kind = (state or {}).get("kind")
    if kind not in PRIOR_KIND_TO_SPEC:
        return "Box" if not kind or kind == "uniform" else str(kind)
    label, params = PRIOR_KIND_TO_SPEC[kind]
    values = ", ".join(f"{float(state[k]):.4g}" for k, _l, _d in params if k in state)
    return f"{label}({values})"


_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def parse(text: str, seed: float) -> tuple[bool, dict | None]:
    """Read a typed prior (``Gaussian``, ``Gaussian(4, 0.4)``, ``box``, ``-``) into a state.

    Parameters
    ----------
    text : str
        A family label or ``kind`` (case-insensitive), optionally followed by its shape
        parameters in the order the catalogue lists them. ``Box``, ``none`` or empty clears the prior.
    seed : float
        The parameter's value, which seeds the shape parameters the text leaves out.

    Returns
    -------
    tuple
        ``(True, state)`` (``state`` is ``None`` for Box) or ``(False, None)`` for text that
        names no family.
    """
    raw = str(text or "").strip()
    head = re.split(r"[\s(]", raw, maxsplit=1)[0].lower() if raw else ""
    if raw.lower().startswith(("box", "none", "-", "uniform")) or not raw:
        return True, None
    chosen = None
    lowered = raw.lower()
    for label, kind, _params in sorted(PRIOR_FAMILY_SPECS, key=lambda s: -len(s[0])):
        if lowered.startswith(label.lower()) or head == kind:
            chosen = kind
            break
    if chosen is None:
        return False, None
    state = seeded_prior_state(chosen, seed)
    numbers = [float(n) for n in _NUMBER.findall(raw[raw.find("(") + 1 :] if "(" in raw else "")]
    for (key, _label, _default), number in zip(PRIOR_KIND_TO_SPEC[chosen][1], numbers):
        state[key] = number
    return True, state
