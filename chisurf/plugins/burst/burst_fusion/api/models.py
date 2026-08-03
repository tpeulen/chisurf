"""Settings and result objects of the burst-fusion step."""

from __future__ import annotations

import dataclasses
from typing import Any

__all__ = ["FusionSettings", "MeasurementFusion", "FusionAnalysis"]


@dataclasses.dataclass
class FusionSettings:
    """What the user chooses when fusing recurring bursts.

    The one number that matters is :attr:`threshold` — the probability, below
    which two bursts are no longer taken to be the same molecule. Everything
    else shapes the ``P_same(tau)`` estimate that the threshold is read against.

    Attributes
    ----------
    threshold : float
        Same-molecule probability required to fuse two consecutive bursts.
        ``1`` fuses nothing; low values eventually merge different molecules.
    tau_min_s, tau_max_s : float
        Lag range over which ``P_same(tau)`` is estimated (seconds, log-spaced).
        ``tau_max_s`` also bounds the recurrence window: a threshold the curve
        never falls below inside the range yields an *unresolved* window.
    n_bins : int
        Logarithmic lag bins.
    min_pairs : int
        Counted burst pairs a lag bin needs before it is allowed to end the
        fusion window. Guards against a hole in sparse statistics reading as a
        confident "different molecule".
    max_gap_ms : float
        Hard ceiling on the gap fusion may bridge, whatever the probability says
        (``0`` removes it). This is not a second opinion about the molecule — it
        is about what a fused burst *costs*. A burst on disk is one interval, so
        bridging a gap puts the photons in that gap inside the burst, and at a
        few kHz of background a 70 ms gap adds hundreds of background photons to
        a burst that had a few hundred real ones. At low concentration ``P_same``
        legitimately stays high out to tens of milliseconds — the molecule really
        is the same one — so without this ceiling a perfectly correct threshold
        produces bursts no downstream fit should see. The default admits the
        split-passage case (gaps of microseconds to a few milliseconds) and
        stops there.
    max_group : int
        Largest number of bursts one fused burst may contain (``0`` = no limit).
    pool_measurements : bool
        Estimate one ``P_same`` curve from all measurements of the folder
        (lags always stay inside a measurement) instead of one curve per file.
        Pooling is the default because a single short file rarely carries enough
        burst pairs to resolve the curve.
    file_type : str
        TTTR container type used to reopen the raw measurements when the fused
        folder is written. ``"auto"`` lets the library identify it; the burst
        folder's own reading manifest wins over this when it has one.
    write_source_companion : bool
        Also write a ``fu4`` companion into the **source** folder recording,
        per original burst, which fused burst it went into — so the grouping can
        be inspected (or gated on) without opening the fused folder.
    """

    threshold: float = 0.5
    tau_min_s: float = 1e-4
    tau_max_s: float = 1.0
    n_bins: int = 60
    min_pairs: int = 3
    max_gap_ms: float = 10.0
    max_group: int = 0
    pool_measurements: bool = True
    file_type: str = "auto"
    write_source_companion: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable copy of the settings."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> FusionSettings:
        """Build settings from a payload, ignoring keys this version lacks."""
        payload = dict(payload or {})
        fields = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in payload.items() if k in fields})


@dataclasses.dataclass
class MeasurementFusion:
    """The fusion of one measurement's bursts.

    Attributes
    ----------
    stem : str
        Measurement stem, the ``.bur`` file name without its suffix.
    source : pandas.DataFrame
        The original burst rows (zero rows removed), in time order.
    fused : pandas.DataFrame
        The table-level merge of those rows — the preview, not the emitted file.
    labels : numpy.ndarray
        Group label per source burst.
    """

    stem: str
    source: Any
    fused: Any
    labels: Any


@dataclasses.dataclass
class FusionAnalysis:
    """Everything a fusion run produced, before anything is written.

    Attributes
    ----------
    folder : pathlib.Path
        The source burst-analysis folder.
    settings : FusionSettings
        The settings it ran with.
    window : chisurf.core.fluorescence.burst.fusion.FusionWindow
        The pooled ``P_same`` curve and the recurrence window the threshold
        implies. With ``pool_measurements=False`` this is the pooled curve kept
        for display, while each measurement fused on its own window.
    windows_by_stem : dict
        Per-measurement windows (identical objects when pooling).
    tau_used_s : float
        The window bursts were actually grouped on — the curve's window capped
        by ``max_gap_ms``. It is this, not ``window.tau_max_s``, that describes
        the emitted folder; the two differ exactly when the ceiling bound.
    measurements : list of MeasurementFusion
        One entry per ``.bur`` file, in folder order.
    statistics : dict
        Burst counts, group sizes and the before/after observables.
    """

    folder: Any
    settings: FusionSettings
    window: Any
    windows_by_stem: dict[str, Any]
    tau_used_s: float
    measurements: list[MeasurementFusion]
    statistics: dict[str, Any]
