"""Plan FCS sample dilutions as fool-proof, step-by-step operator recipes.

The people following :func:`plan_dilution` have never done an FCS preparation.
The plan therefore never says "dilute 1:6" or "take C1*V2/C2 microliters" --
it computes everything itself and returns one plain sentence per physical
action, with the microliters spelled out::

    Put 42.0 uL buffer on the slide, add 8.0 uL of the FCS stock.

If the neat stock would need a pipetted volume too small to take reliably
(below ``min_take_ul``), the plan inserts explicit 1:10 pre-dilution mixes
first (``max_pre_steps`` caps how many) and dilutes from the pre-dilution.

All concentrations share one unit (caller converts; use :func:`format_conc`
to render).  Volumes are quantised to ``volume_step_ul``; the buffer volume
is chosen so the final volume always sums to exactly ``target_volume_ul``.
Everything is pure math -- no hardware, no GUI, no unit surprises: the
achieved concentration is computed from the *rounded* volumes actually
piped, never from the ideal ones.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

__all__ = ["DilutionStep", "DilutionPlan", "plan_dilution",
           "recommended_pre_dilution_factor", "format_conc"]

REL_ERROR_TOLERANCE = 0.10


def _ul(value: float) -> str:
    """Format a microliter volume the way operators read it: one decimal."""
    return f"{value:.1f}"


def format_conc(value: float, unit: str = "pM") -> str:
    """Render a concentration for display, e.g. ``format_conc(51.2) -> '51.2 pM'``."""
    return f"{value:.4g} {unit}"


@dataclass
class DilutionStep:
    """One physical action: take ``take_ul`` of a source into ``into_ul``.

    ``conc_after`` is the concentration in the mixed volume ``total_ul``,
    computed from these exact (already rounded) volumes.
    """
    action: str
    take_ul: float
    into_ul: float
    total_ul: float
    conc_after: float
    label: str


@dataclass
class DilutionPlan:
    """A complete dilution recipe plus its honest outcome numbers."""
    steps: list = field(default_factory=list)
    instruction_lines: list = field(default_factory=list)
    achieved_conc: float = 0.0
    rel_error: float = 0.0
    direct: bool = True
    ok: bool = True
    reason: str | None = None


def _quantise(volume: float, step: float) -> float:
    """Round ``volume`` to the nearest multiple of ``step`` (no banker's rounding)."""
    return math.floor(volume / step + 0.5) * step


def plan_dilution(stock_conc, target_conc, *, target_volume_ul=50.0,
                  min_take_ul=2.0, volume_step_ul=0.5,
                  pre_dilution_volume_ul=50.0, max_pre_steps=2,
                  allow_direct_use=False):
    """Plan how to reach ``target_conc`` from ``stock_conc`` in plain steps.

    Returns a :class:`DilutionPlan`.  Raises ``ValueError`` for nonpositive
    or NaN concentrations/volumes, ``min_take_ul <= 0`` or a target already
    at/above the stock concentration (pass ``allow_direct_use=True`` to get
    a "use as-is" plan instead).  When even ``max_pre_steps`` pre-dilutions
    cannot make the final take pipetting-safe, the plan is returned with
    ``ok=False`` and a ``reason`` -- never an invented recipe.
    """
    for name, value in (("stock", stock_conc), ("target", target_conc)):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} concentration must be a positive finite number, got {value!r}")
    if stock_conc <= target_conc:
        if allow_direct_use:
            return _as_is_plan(stock_conc, target_volume_ul)
        raise ValueError(
            f"Nothing to dilute: stock concentration ({format_conc(stock_conc)}) is already "
            f"at or above the target ({format_conc(target_conc)}). Use the stock as-is.")
    if min_take_ul <= 0:
        raise ValueError(f"min_take_ul must be > 0, got {min_take_ul}")
    if target_volume_ul <= 0:
        raise ValueError(f"target_volume_ul must be > 0, got {target_volume_ul}")
    if volume_step_ul <= 0:
        raise ValueError(f"volume_step_ul must be > 0, got {volume_step_ul}")
    if pre_dilution_volume_ul <= 0:
        raise ValueError(f"pre_dilution_volume_ul must be > 0, got {pre_dilution_volume_ul}")

    take = _quantise(target_volume_ul * target_conc / stock_conc, volume_step_ul)
    if take < min_take_ul:
        return _plan_with_pre_dilutions(
            stock_conc, target_conc, target_volume_ul, min_take_ul,
            volume_step_ul, pre_dilution_volume_ul, max_pre_steps)
    buffer_ul = target_volume_ul - take
    conc = stock_conc * take / target_volume_ul
    rel_err = abs(conc - target_conc) / target_conc
    step = DilutionStep(
        action=f"Add {_ul(take)} uL of the FCS stock to {_ul(buffer_ul)} uL buffer",
        take_ul=take, into_ul=buffer_ul, total_ul=target_volume_ul,
        conc_after=conc, label="the FCS stock")
    line = (f"Put {_ul(buffer_ul)} uL buffer on the slide, "
            f"add {_ul(take)} uL of the FCS stock.")
    ok = rel_err <= REL_ERROR_TOLERANCE
    return DilutionPlan(
        steps=[step], instruction_lines=[line], achieved_conc=conc,
        rel_error=rel_err, direct=True, ok=ok,
        reason=None if ok else (
            f"Rounding to {_ul(volume_step_ul)} uL steps gives "
            f"{rel_err * 100:.1f}% error (>{REL_ERROR_TOLERANCE * 100:.0f}% allowed); "
            f"use a finer volume step."))


def _as_is_plan(stock_conc, target_volume_ul):
    """Plan for 'the concentration is already right': pipette the stock as-is."""
    step = DilutionStep(
        action=f"Use {_ul(target_volume_ul)} uL of the FCS stock as-is",
        take_ul=target_volume_ul, into_ul=0.0, total_ul=target_volume_ul,
        conc_after=stock_conc, label="the FCS stock")
    line = f"Put {_ul(target_volume_ul)} uL of the FCS stock on the slide, no dilution needed."
    return DilutionPlan(steps=[step], instruction_lines=[line],
                        achieved_conc=stock_conc, rel_error=0.0, direct=True, ok=True)


def _plan_with_pre_dilutions(stock_conc, target_conc, target_volume_ul, min_take_ul,
                             volume_step_ul, pre_volume_ul, max_pre_steps):
    """Build a plan that chains 1:10 pre-dilution mixes until the take is safe."""
    factor = recommended_pre_dilution_factor(
        stock_conc, target_conc, min_take_ul, target_volume_ul)
    n_steps = int(round(math.log10(factor)))
    if n_steps > max_pre_steps:
        return DilutionPlan(
            ok=False, direct=False,
            reason=(f"The stock is too concentrated: even after {max_pre_steps} "
                    f"pre-dilution(s) of 1:10 the required take would still be below "
                    f"{_ul(min_take_ul)} uL. Prepare a more dilute stock first."))
    steps, lines = [], []
    conc = stock_conc
    source = "the FCS stock"
    for i in range(1, n_steps + 1):
        conc = conc / 10.0
        factor_so_far = 10 ** i
        stock_ul = pre_volume_ul / 10.0
        buffer_ul = pre_volume_ul - stock_ul
        steps.append(DilutionStep(
            action=f"Mix {_ul(stock_ul)} uL of {source} with {_ul(buffer_ul)} uL buffer",
            take_ul=stock_ul, into_ul=buffer_ul, total_ul=pre_volume_ul,
            conc_after=conc, label=f"pre-dilution (1:{factor_so_far})"))
        lines.append(f"Mix {_ul(stock_ul)} uL of {source} with "
                     f"{_ul(buffer_ul)} uL buffer (1:{factor_so_far} pre-dilution).")
        source = f"the pre-dilution (1:{factor_so_far})"
    take = _quantise(target_volume_ul * target_conc / conc, volume_step_ul)
    if take < min_take_ul:
        return DilutionPlan(
            ok=False, direct=False, steps=steps, instruction_lines=lines,
            reason=(f"After {n_steps} pre-dilution(s) of 1:10 the take would still be "
                    f"{_ul(take)} uL (< {_ul(min_take_ul)} uL minimum)."))
    buffer_ul = target_volume_ul - take
    final_conc = conc * take / target_volume_ul
    rel_err = abs(final_conc - target_conc) / target_conc
    overall = int(round(stock_conc / conc))
    steps.append(DilutionStep(
        action=f"Add {_ul(take)} uL of the pre-dilution to {_ul(buffer_ul)} uL buffer",
        take_ul=take, into_ul=buffer_ul, total_ul=target_volume_ul,
        conc_after=final_conc, label=f"the pre-dilution (1:{overall})"))
    lines.append(f"Put {_ul(buffer_ul)} uL buffer on the slide, "
                 f"add {_ul(take)} uL of the pre-dilution (1:{overall}).")
    ok = rel_err <= REL_ERROR_TOLERANCE
    return DilutionPlan(
        steps=steps, instruction_lines=lines, achieved_conc=final_conc,
        rel_error=rel_err, direct=False, ok=ok,
        reason=None if ok else (
            f"Rounding gives {rel_err * 100:.1f}% error "
            f"(>{REL_ERROR_TOLERANCE * 100:.0f}% allowed)."))


def recommended_pre_dilution_factor(stock_conc, target_conc, min_take_ul, total_volume_ul):
    """Smallest 1:10^k pre-dilution making the final take pipetting-safe.

    Returns 1.0 when the direct take is already ``>= min_take_ul``, else the
    smallest power of ten whose pre-diluted stock allows a final take of at
    least ``min_take_ul`` from ``total_volume_ul``.  Used by the wizard.
    """
    direct_take = total_volume_ul * target_conc / stock_conc
    if direct_take >= min_take_ul:
        return 1.0
    factor = min_take_ul * stock_conc / (total_volume_ul * target_conc)
    return 10.0 ** math.ceil(math.log10(factor))
