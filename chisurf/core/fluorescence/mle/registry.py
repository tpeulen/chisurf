"""The MLE lifetime fit models tttrlib advertises.

A thin view onto the ``fit`` category of :mod:`chisurf.core.tttrlib_registry`
(the same machine-readable registry that publishes burst searches). tttrlib
describes each estimator — fit23/24/25/26 — with a label, summary, description
and a JSON-Schema ``params_schema`` giving each optimisable parameter's type,
default, range, unit and ``fixed_default``. chisurf renders that schema into the
fit-parameter form, so a fit model added to tttrlib appears in the GUI on upgrade
with no chisurf change (mirrors :mod:`chisurf.core.fluorescence.burst.tttrlib_search`).
"""

from __future__ import annotations

import typing

from chisurf.core import tttrlib_registry


def fit_models() -> dict[str, dict[str, typing.Any]]:
    """Return the lifetime fit models tttrlib advertises, keyed by model name.

    Returns an empty dict when the installed tttrlib publishes no fit registry,
    so callers can fall back to a hand-authored fit-parameter form.

    Returns
    -------
    dict
        ``{name: {"name", "label", "summary", "description", "method",
        "setup", "params_schema"}}``.
    """
    return tttrlib_registry.entries(tttrlib_registry.FIT_MODEL)


def is_available() -> bool:
    """Whether the installed tttrlib publishes the fit-model registry."""
    return bool(fit_models())
