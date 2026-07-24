"""Shared dynamic bunching / anticorrelation relaxation-term groups for FCS models.

Reused by both the Enderlein-MDF model (:mod:`chisurf.core.models.fcs.mdf`) and
the general composable FCS model (:mod:`chisurf.core.models.fcs.general`) so the
add/remove-a-relaxation-term editor UI and formula convention exist in one
place. The multiplicative forms match the FCS parse-model catalogue
(``chisurf/core/models/fcs/models.yaml``): bunching terms are
``(1 - a_i + a_i * exp(-tau/t_i))`` (a plateau-shifting relaxation, e.g.
triplet/blinking, microsecond-to-millisecond timescale); anticorrelation
(photon-antibunching) terms are ``(1 - a_i * exp(-tau/t_i))`` (a pure
sub-Poissonian dip, no plateau shift, nanosecond timescale). Each ``add_*``
call defaults its new term's time constant to the next decade up from the
previous term (1, 10, 100, ... µs for bunching; 1, 10, 100, ... ns for
anticorrelation) so a user adding several terms gets a sensibly spread-out
starting point instead of stacked duplicates.
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

    def add_bunching(
        self, ba: float = 0.1, bt: typing.Optional[float] = None, fixed: bool = False, **kwargs
    ) -> None:
        """Add one bunching term.

        ``bt`` (time constant, ms) defaults to the next decade up from the
        previous term when omitted: 0.001 ms (1 µs), 0.01 ms (10 µs), 0.1 ms
        (100 µs), ...
        """
        i = len(self) + 1
        if bt is None:
            bt = 0.001 * (10 ** (i - 1))
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

    def equation_html(self) -> str:
        """HTML factor chain for the active bunching terms (for a compound-equation display)."""
        return " &middot; ".join(
            f"(1 &minus; a<sub>b{i}</sub> + a<sub>b{i}</sub>&middot;"
            f"e<sup>&minus;&tau;/&tau;<sub>b{i}</sub></sup>)"
            for i in range(1, len(self) + 1)
        )


class AnticorrTerms(FittingParameterGroup):
    """Zero or more photon-anticorrelation (antibunching) dip terms."""

    def __init__(self, name: str = "anticorr", **kwargs):
        """Initialize with no anticorrelation terms; add them via :meth:`add_anticorr`."""
        super().__init__(name=name, **kwargs)
        self._aca: typing.List[FittingParameter] = []
        self._act: typing.List[FittingParameter] = []

    def __len__(self) -> int:
        """Return the number of active anticorrelation terms."""
        return len(self._aca)

    def terms(self) -> typing.List[typing.Tuple[float, float]]:
        """Return ``[(amplitude, time_constant_ns), ...]`` for the active terms."""
        return [(float(a.value), float(t.value)) for a, t in zip(self._aca, self._act)]

    def _anticorr_parameter_rows(self) -> list:
        """Interleaved ``(amplitude, time_constant)`` rows for the dynamic table."""
        rows = []
        for a, t in zip(self._aca, self._act):
            rows.append(a)
            rows.append(t)
        return rows

    def add_anticorr(
        self, aca: float = 0.5, act: typing.Optional[float] = None, fixed: bool = False, **kwargs
    ) -> None:
        """Add one anticorrelation term.

        ``act`` (time constant, ns) defaults to the next decade up from the
        previous term when omitted: 1, 10, 100, ... ns.
        """
        i = len(self) + 1
        if act is None:
            act = 1.0 * (10 ** (i - 1))
        a = FittingParameter(
            value=aca, name=f"aca{i}", lb=0.0, ub=1.0, fixed=fixed,
            label_text=f"a<sub>ac{i}</sub>", registry_id="fcs.anticorr.aca")
        t = FittingParameter(
            value=act, name=f"act{i}", lb=1e-3, ub=1e6, fixed=fixed,
            label_text=f"&tau;<sub>ac{i}</sub>[ns]", registry_id="fcs.anticorr.act")
        self._aca.append(a)
        self._act.append(t)

    def remove_anticorr(self) -> None:
        """Remove the last anticorrelation term, if any."""
        if self._aca:
            self._aca.pop()
            self._act.pop()

    def apply(self, g: np.ndarray, tau_ms: np.ndarray) -> np.ndarray:
        """Multiply ``g`` by every active anticorrelation term's dip factor."""
        for aca, act_ns in self.terms():
            act_ms = act_ns * 1e-6
            if act_ms > 0:
                g = g * (1.0 - aca * np.exp(-tau_ms / act_ms))
        return g

    def equation_html(self) -> str:
        """HTML factor chain for the active anticorrelation terms (for a compound-equation display)."""
        return " &middot; ".join(
            f"(1 &minus; a<sub>ac{i}</sub>&middot;e<sup>&minus;&tau;/&tau;<sub>ac{i}</sub></sup>)"
            for i in range(1, len(self) + 1)
        )
