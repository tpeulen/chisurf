"""Show a parameter stored in seconds (or counts/s) in the unit that reads best: µs, ms, s (kcps).

A registry schema (tttrlib's burst searches) stores times in seconds, so a sliding-window duration
of 0.5 ms appeared as ``0.0005``. :func:`scaled_sections` gives each seconds-valued field of a form
spec a display unit -- chosen once from the parameter's default, so the unit does not jump while
the user types -- and :class:`ScaledParameters` converts between what the form shows and the
seconds the parameter keeps.
"""

from __future__ import annotations

import re
from typing import Any

#: Display units of a time, largest first: (suffix, factor from seconds).
TIME_UNITS = (("s", 1.0), ("ms", 1e3), ("µs", 1e6), ("ns", 1e9))
_SECONDS = {"s", "sec", "second", "seconds"}
#: A unit written into a title ("Bin width (s)"), dropped once the field carries its own suffix.
_TITLE_UNIT = re.compile(r"\s*\((?:s|sec|seconds|cps)\)\s*$")
#: Display units of a count rate, largest first.
RATE_UNITS = (("Mcps", 1e-6), ("kcps", 1e-3), ("cps", 1.0))
_RATE = {"cps", "counts/s", "hz", "1/s"}


def time_unit(seconds: float | None) -> tuple[str, float]:
    """The unit a time of *seconds* reads best in: its value lands in [0.1, 100) where it can (0.5 ms, 50 ms).

    ``0`` or unknown is shown in ms, the scale of a burst (a duration or gap that is off by
    default still reads in the unit its useful values have).
    """
    value = abs(float(seconds or 0.0))
    if value == 0.0:
        return "ms", 1e3
    for suffix, factor in TIME_UNITS:
        if value * factor >= 0.1:
            return suffix, factor
    return TIME_UNITS[-1]


def rate_unit(cps: float | None) -> tuple[str, float]:
    """The unit a count rate reads best in; ``0`` or unknown is kcps (a smFRET background)."""
    value = abs(float(cps or 0.0))
    if value == 0.0:
        return "kcps", 1e-3
    for suffix, factor in RATE_UNITS:
        if value * factor >= 1.0:
            return suffix, factor
    return RATE_UNITS[-1]


def _unit_of(prop: dict[str, Any]) -> tuple[str, float] | None:
    unit = str(prop.get("unit") or "").strip()
    if unit in _SECONDS:
        return time_unit(prop.get("default"))
    if unit.lower() in _RATE and unit != "1/s":
        return rate_unit(prop.get("default"))
    return None


def scaled_sections(
    sections: list[dict[str, Any]], schema: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """*sections* with every seconds-valued number in its display unit, and the factor per attr."""
    props = schema.get("properties") or {}
    out, factors = [], {}
    for section in sections:
        prop = props.get(section.get("attr"), {})
        unit = _unit_of(prop) if section.get("kind") == "float" else None
        if unit is None:
            out.append(section)
            continue
        suffix, factor = unit
        section = dict(section)
        section["label"] = _TITLE_UNIT.sub("", str(section.get("label", "")))
        section["suffix"] = " " + suffix
        section["description"] = re.sub(
            r"Unit: [^.]*\.", f"Unit: {suffix}.", str(section.get("description", ""))
        )
        for bound in ("minimum", "maximum"):
            if section.get(bound) is not None:
                section[bound] = float(section[bound]) * factor
        section.pop("style", None)  # 5e-04 s is 0.5 ms: plain digits now
        section["decimals"] = 3
        factors[section["attr"]] = factor
        out.append(section)
    return out, factors


class ScaledParameters:
    """*target*'s attributes, those named in *factors* multiplied by their factor (read) and divided (write)."""

    def __init__(self, target: Any, factors: dict[str, float]) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_factors", dict(factors))

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        value = getattr(self._target, name)
        factor = self._factors.get(name)
        if factor is None or value is None:
            return value
        return float(value) * factor

    def __setattr__(self, name: str, value: Any) -> None:
        factor = self._factors.get(name)
        if factor is not None and value is not None:
            value = float(value) / factor
            current = getattr(self._target, name, None)
            if current is not None and abs(float(current) - value) <= 1e-12 * max(abs(value), 1e-300):
                return  # the round trip through the display unit is not an edit
        setattr(self._target, name, value)

    def __getitem__(self, name: str) -> Any:  # some forms read values by key
        return self.__getattr__(name)


__all__ = ["RATE_UNITS", "TIME_UNITS", "ScaledParameters", "rate_unit", "scaled_sections", "time_unit"]
