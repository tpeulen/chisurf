"""Request/result dataclasses for the MFD preparation plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PrepareRequest:
    """A request to prepare a burst folder for MFD analysis.

    Parameters
    ----------
    folder : str
        Path to the burst-analysis folder (containing ``.bur`` files and
        co-located TTTR photon sources).
    streams : list of dict, optional
        Explicit stream definitions (``{"name": "green", "channels": [0, 8]}``).
        If omitted, streams are inferred from the burst table and photons.
    with_photons : bool
        Load photon streams for micro-time computation (default ``True``).
    """

    folder: str = ""
    streams: list[dict] | None = None
    with_photons: bool = True


@dataclass
class PrepareResult:
    """The result of preparing a burst folder.

    Wraps the key outputs of
    :func:`~chisurf.core.fluorescence.mfd.prepare.prepare_burst_folder` in a
    JSON-serializable form.
    """

    folder: str = ""
    n_bursts: int = 0
    channels: list[str] = field(default_factory=list)
    verified_channels: list[str] = field(default_factory=list)
    count_agreement: dict[str, float] = field(default_factory=dict)
    duration_s: float = 0.0
    total_photons: int = 0
    report: str = ""
    summary: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "folder": self.folder,
            "n_bursts": self.n_bursts,
            "channels": self.channels,
            "verified_channels": self.verified_channels,
            "count_agreement": self.count_agreement,
            "duration_s": self.duration_s,
            "total_photons": self.total_photons,
            "report": self.report,
            "summary": self.summary,
            "sources": self.sources,
            "error": self.error,
        }
