"""Generic, mixable FRET line computation engine.

A FRET line is computed for a *mixture* of one or more lifetime/FRET models.
Each component is any model registered in MODEL_REGISTRY.  The swept quantity
is either:

  * a parameter of any component model, by canonical id (e.g. ``distance.mean.0``,
    ``chain.contour_length``), or
  * the mixing fraction of any component (for a >1-component mixture).

A single-component mixture reproduces an ordinary single-model FRET line. The
components are BFF-described views and the engine is
:mod:`chisurf.core.fluorescence.fret.fret_line`.
"""

from __future__ import annotations

from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------
# Display name -> the BFF model family whose view is a component. Parameters are
# addressed by canonical id (``distance.mean.0``); the engine is
# chisurf.core.fluorescence.fret.fret_line.

MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "FRET: FD (Gaussian)": {"family": "tcspc_fret_gaussian"},
    "FRET: FD (Worm-like chain)": {"family": "tcspc_fret_worm_like_chain"},
    "FRET: FD (Discrete)": {"family": "tcspc_fret_discrete"},
    "FRET: Fixed distance": {"family": "tcspc_fret_discrete"},
    "Lifetime": {"family": "tcspc_lifetime"},
}


def list_models() -> list[str]:
    """Return the display names of all registered component models."""
    return list(MODEL_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_component(model_name: str, n_components: int = 1):
    """A view of the registered model with ``n_components`` components."""
    from chisurf.core.fluorescence.fret.fret_line import model_view

    entry = MODEL_REGISTRY.get(model_name)
    if entry is None:
        raise ValueError(f"Unknown model {model_name!r}. Choose from {list_models()}")
    return model_view(entry["family"], n_components)


def _canonical(parameter) -> str:
    return getattr(parameter, "canonical_id", parameter.name)


def _parameters_of(model) -> list:
    """The parameters the model's current structure uses, in registry order."""
    used = set(model.structure_parameter_ids())
    return [p for p in model.parameters_all if _canonical(p) in used]


def _normalize_components(components) -> list[dict]:
    """Validate / normalize the component spec list."""
    if not components:
        raise ValueError("At least one component is required.")
    return [
        {
            "model_name": c["model_name"],
            "n_components": int(c.get("n_components", 1)),
            "params": dict(c.get("params") or {}),
        }
        for c in components
    ]


def get_model_parameters(model_name: str, n_components: int = 1) -> list[dict]:
    """Return the parameters of a freshly built model.

    Each item is ``{"name": <canonical id>, "label": str, "value": float, "fixed": bool}``.
    """
    model = _build_component(model_name, n_components)
    return [
        {"name": _canonical(p), "label": p.name, "value": float(p.value), "fixed": bool(p.fixed)}
        for p in _parameters_of(model)
    ]


# ---------------------------------------------------------------------------
# Sweep core (shared by the spec-based and instance-based entry points)
# ---------------------------------------------------------------------------

#: Parameter groups that never meaningfully sweep a FRET line: the instrument,
#: the anisotropy decay and the donor-only fraction. Hidden by default in the
#: sweep-target list (``relevant_only=True``).
_NUISANCE_PREFIXES: tuple[str, ...] = ("instrument.", "anisotropy.", "rotation.")
NUISANCE_PARAMS: frozenset[str] = frozenset({"fret.x_donly"})


def _is_relevant(name: str) -> bool:
    """Return True if the canonical id *name* is a meaningful sweep target."""
    return name not in NUISANCE_PARAMS and not name.startswith(_NUISANCE_PREFIXES)


def _targets_for_models(models, names: list[str] | None = None, relevant_only: bool = True) -> list[dict]:
    """Build sweep targets from already-built views."""
    def display(ci, model):
        return names[ci] if names and ci < len(names) else getattr(model, "name", type(model).__name__)

    targets: list[dict] = []
    for ci, model in enumerate(models):
        for p in _parameters_of(model):
            name = _canonical(p)
            if relevant_only and not _is_relevant(name):
                continue
            targets.append({"label": f"C{ci} [{display(ci, model)}] · {p.name}", "kind": "param",
                            "component": ci, "name": name})
    if len(models) > 1:
        for ci, model in enumerate(models):
            targets.append({"label": f"fraction · C{ci} [{display(ci, model)}]", "kind": "fraction",
                            "component": ci, "name": None})
    return targets


def _run_sweep(models, sweep: dict, param_min: float, param_max: float, n_points: int,
               fractions: list[float] | None, tau_d0: float | None, log_scale: bool) -> dict:
    """Sweep the requested quantity over the mixed views; ``ValueError`` on a bad spec."""
    from chisurf.core.fluorescence.fret.fret_line import sweep as fret_line_sweep

    if log_scale:
        if param_min <= 0 or param_max <= 0:
            raise ValueError("Log-scale sweep requires param_min and param_max > 0.")
        values = np.geomspace(float(param_min), float(param_max), int(n_points))
    else:
        values = np.linspace(float(param_min), float(param_max), int(n_points))
    return fret_line_sweep(models, sweep, values, fractions=fractions, tau_d0=tau_d0)


# ---------------------------------------------------------------------------
# Public API — spec-based (headless: CLI / RPC / tests)
# ---------------------------------------------------------------------------


def list_sweep_targets(components: list[dict], relevant_only: bool = True) -> list[dict]:
    """Enumerate sweepable parameters/fractions for a component *spec* list.

    Each target::

        {"label": str, "kind": "param"|"fraction", "component": int, "name": str|None}

    When *relevant_only* is True nuisance parameters are omitted.
    """
    comps = _normalize_components(components)
    models = [_build_component(c["model_name"], c["n_components"]) for c in comps]
    return _targets_for_models(models, [c["model_name"] for c in comps], relevant_only)


def compute_fret_line(
    components: list[dict],
    sweep: dict,
    param_min: float,
    param_max: float,
    n_points: int = 100,
    fractions: list[float] | None = None,
    tau_d0: float | None = None,
    log_scale: bool = False,
) -> dict:
    """Compute a FRET line for a mixture of models built from specs.

    Parameters
    ----------
    components : list of dict
        One entry per mixture component::

            {"model_name": str, "n_components": int, "params": {canonical id: value}}

    sweep : dict
        What to vary::

            {"kind": "param", "component": int, "name": str}   # a parameter's canonical id
            {"kind": "fraction", "component": int}             # a mixing fraction

    param_min, param_max : float
        Sweep range endpoints.
    n_points : int
        Number of sweep points.
    fractions : list of float, optional
        Initial mixing weights (one per component). Defaults to equal weights.
    tau_d0 : float, optional
        Reference donor lifetime for E_FRET = 1 − τ_X / τ_D0. Auto-detected
        from the first FRET component when not supplied.
    log_scale : bool
        Logarithmic sweep spacing (both endpoints must be > 0) when True.

    Returns
    -------
    dict
        ``{"ok": True, "result": {...}}`` or ``{"ok": False, "error": "..."}``.
    """
    try:
        comps = _normalize_components(components)
        models = []
        from chisurf.core.fluorescence.fret.fret_line import find_parameter

        for c in comps:
            m = _build_component(c["model_name"], c["n_components"])
            for k, v in c["params"].items():
                find_parameter(m, k).value = float(v)
            models.append(m)
        result = _run_sweep(
            models, sweep, param_min, param_max, n_points, fractions, tau_d0, log_scale
        )
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Public API — instance-based (GUI: live widget-models)
# ---------------------------------------------------------------------------


def sweep_targets_for_models(
    models, names: list[str] | None = None, relevant_only: bool = True
) -> list[dict]:
    """Enumerate sweepable parameters/fractions for live model instances.

    When *relevant_only* is True nuisance parameters are omitted.
    """
    return _targets_for_models(models, names, relevant_only)


#: Which result arrays map to the plotted x / y for a FRET-line overlay.
_FRET_LINE_AXES: dict[str, tuple[str, str, str]] = {
    # key: (x_array, y_array, human axes label)
    "static": ("tau_f", "e_fret", "E vs fluorescence-averaged lifetime"),
    "e_vs_tau_x": ("tau_x", "e_fret", "E vs species-averaged lifetime"),
    "tau_x_vs_tau_f": ("tau_f", "tau_x", "species- vs fluorescence-averaged lifetime"),
}


def fret_line_overlays(
    components: list[dict],
    sweep: dict,
    param_min: float,
    param_max: float,
    n_points: int = 100,
    fractions: list[float] | None = None,
    tau_d0: float | None = None,
    log_scale: bool = False,
    line: str = "static",
    name: str = "FRET line",
    style: dict | None = None,
) -> dict:
    """Compute a FRET line and return it as a shared overlay LineSet.

    Wraps :func:`compute_fret_line` and reshapes its result into the same
    ``{"overlays": [{"name", "kind", "x", "y", "style", "axes"}]}`` contract that
    ``phasor.overlays`` returns, so ndX (and any other client) can draw FRET
    lines and phasor lines through one uniform interface.

    Parameters
    ----------
    components, sweep, param_min, param_max, n_points, fractions, tau_d0, log_scale
        Passed straight through to :func:`compute_fret_line` (see there).
    line : str
        Which projection to emit: ``"static"`` (E vs τ_f, the default),
        ``"e_vs_tau_x"`` (E vs τ_x) or ``"tau_x_vs_tau_f"`` (τ_x vs τ_f).
    name : str
        Label for the returned line.
    style : dict, optional
        pyqtgraph-style hints (``color``, ``width``, ``dash``); defaults to a solid line.
    """
    res = compute_fret_line(
        components, sweep, param_min, param_max, n_points, fractions, tau_d0, log_scale
    )
    if not res.get("ok"):
        return res
    if line not in _FRET_LINE_AXES:
        return {"ok": False, "error": f"unknown line projection {line!r}; choose {sorted(_FRET_LINE_AXES)}"}
    x_key, y_key, axes_label = _FRET_LINE_AXES[line]
    result = res["result"]
    overlay = {
        "name": name,
        "kind": "curve",
        "x": result[x_key],
        "y": result[y_key],
        "style": style or {"color": "#50c0ff", "width": 2},
        "axes": {"x": x_key, "y": y_key, "label": axes_label},
    }
    return {"ok": True, "result": {"overlays": [overlay], "line": line}}


def list_fret_line_projections() -> list[str]:
    """Return the available FRET-line overlay projections for :func:`fret_line_overlays`."""
    return list(_FRET_LINE_AXES.keys())


def compute_fret_line_for_models(
    models,
    sweep: dict,
    param_min: float,
    param_max: float,
    n_points: int = 100,
    fractions: list[float] | None = None,
    tau_d0: float | None = None,
    log_scale: bool = False,
) -> dict:
    """Compute a FRET line by sweeping over already-built model instances.

    Used by the GUI, which edits live widget-models with the native fitting
    editors and passes them here directly (no rebuild from specs).
    """
    try:
        result = _run_sweep(
            models, sweep, param_min, param_max, n_points, fractions, tau_d0, log_scale
        )
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
