"""Shared dynamic bunching / antibunching relaxation-term groups for FCS models.

Reused by both the Enderlein-MDF model (:mod:`chisurf.core.models.fcs.mdf`) and
the general composable FCS model (:mod:`chisurf.core.models.fcs.general`) so the
add/remove-a-relaxation-term editor UI and formula convention exist in one
place. The multiplicative forms match the FCS parse-model catalogue
(``chisurf/core/models/fcs/models.yaml``): bunching terms are
``(1 - a_i + a_i * exp(-tau/t_i))`` (a plateau-shifting relaxation, e.g.
triplet/blinking); antibunching terms are ``(1 - a_i * exp(-tau/t_i))`` (a pure
sub-Poissonian dip, no plateau shift).
"""

from __future__ import annotations

import numpy as np

from chisurf import typing
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup


class BunchingTerms(FittingParameterGroup):
    """Zero or more exponential bunching/blinking relaxation terms."""

    def __init__(self, name: str = "bunching", **kwargs):
        """Initialize with no bunching terms; add them via :meth:`add_bunching`."""
        super().__init__(name=name, **kwargs)
        self._ba: typing.List[FittingParameter] = []
        self._bt: typing.List[FittingParameter] = []

    def __len__(self) -> int:
        """Return the number of active bunching terms."""
        return len(self._ba)

    def terms(self) -> typing.List[typing.Tuple[float, float]]:
        """Return ``[(amplitude, time_constant_ms), ...]`` for the active terms."""
        return [(float(a.value), float(t.value)) for a, t in zip(self._ba, self._bt)]

    def _bunching_parameter_rows(self) -> list:
        """Interleaved ``(amplitude, time_constant)`` rows for the dynamic table."""
        rows = []
        for a, t in zip(self._ba, self._bt):
            rows.append(a)
            rows.append(t)
        return rows

    def add_bunching(self, ba: float = 0.1, bt: float = 0.001, fixed: bool = False, **kwargs) -> None:
        """Add one bunching term (default amplitude 0.1, time constant 1 µs)."""
        i = len(self) + 1
        a = FittingParameter(
            value=ba, name=f"ba{i}", lb=0.0, ub=0.999, fixed=fixed,
            label_text=f"a<sub>b{i}</sub>", registry_id="fcs.bunching.ba")
        t = FittingParameter(
            value=bt, name=f"bt{i}", lb=1e-6, ub=1e3, fixed=fixed,
            label_text=f"&tau;<sub>b{i}</sub>[ms]", registry_id="fcs.bunching.bt")
        self._ba.append(a)
        self._bt.append(t)

    def remove_bunching(self) -> None:
        """Remove the last bunching term, if any."""
        if self._ba:
            self._ba.pop()
            self._bt.pop()

    def apply(self, g: np.ndarray, tau_ms: np.ndarray) -> np.ndarray:
        """Multiply ``g`` by every active bunching term's relaxation factor."""
        for ba, bt in self.terms():
            if bt > 0:
                g = g * (1.0 - ba + ba * np.exp(-tau_ms / bt))
        return g


class AntibunchingTerms(FittingParameterGroup):
    """Zero or more photon-antibunching dip terms."""

    def __init__(self, name: str = "antibunching", **kwargs):
        """Initialize with no antibunching terms; add them via :meth:`add_antibunching`."""
        super().__init__(name=name, **kwargs)
        self._aba: typing.List[FittingParameter] = []
        self._abt: typing.List[FittingParameter] = []

    def __len__(self) -> int:
        """Return the number of active antibunching terms."""
        return len(self._aba)

    def terms(self) -> typing.List[typing.Tuple[float, float]]:
        """Return ``[(amplitude, time_constant_ms), ...]`` for the active terms."""
        return [(float(a.value), float(t.value)) for a, t in zip(self._aba, self._abt)]

    def _antibunching_parameter_rows(self) -> list:
        """Interleaved ``(amplitude, time_constant)`` rows for the dynamic table."""
        rows = []
        for a, t in zip(self._aba, self._abt):
            rows.append(a)
            rows.append(t)
        return rows

    def add_antibunching(self, aba: float = 0.5, abt: float = 0.0001, fixed: bool = False, **kwargs) -> None:
        """Add one antibunching term (default amplitude 0.5, time constant 100 ns)."""
        i = len(self) + 1
        a = FittingParameter(
            value=aba, name=f"aba{i}", lb=0.0, ub=1.0, fixed=fixed,
            label_text=f"a<sub>ab{i}</sub>", registry_id="fcs.antibunching.aba")
        t = FittingParameter(
            value=abt, name=f"abt{i}", lb=1e-9, ub=1.0, fixed=fixed,
            label_text=f"&tau;<sub>ab{i}</sub>[ms]", registry_id="fcs.antibunching.abt")
        self._aba.append(a)
        self._abt.append(t)

    def remove_antibunching(self) -> None:
        """Remove the last antibunching term, if any."""
        if self._aba:
            self._aba.pop()
            self._abt.pop()

    def apply(self, g: np.ndarray, tau_ms: np.ndarray) -> np.ndarray:
        """Multiply ``g`` by every active antibunching term's dip factor."""
        for aba, abt in self.terms():
            if abt > 0:
                g = g * (1.0 - aba * np.exp(-tau_ms / abt))
        return g
