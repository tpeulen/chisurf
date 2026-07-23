"""Data models for the 2CDE API."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TwoCdeSettings:
    """FRET-2CDE / ALEX-2CDE settings.

    Attributes
    ----------
    donor_channels : list of int
        Donor routing channels (donor-excitation stream for ``variant="alex"``).
    donor_micro_time_ranges : list of tuple[int, int]
        Inclusive micro-time windows for the donor stream.
    acceptor_channels : list of int
        Acceptor routing channels.
    acceptor_micro_time_ranges : list of tuple[int, int]
        Inclusive micro-time windows for the acceptor stream.
    acceptor_excitation_channels : list of int
        Acceptor-excitation channels (ALEX-2CDE only; empty reuses acceptor).
    acceptor_excitation_micro_time_ranges : list of tuple[int, int]
        Micro-time windows for the acceptor-excitation stream (ALEX-2CDE only).
    tau : float
        Kernel time constant in seconds.
    kernel : str
        ``"laplace"`` (Tomov original) or ``"gaussian"``.
    variant : str
        ``"fret"`` (FRET-2CDE) or ``"alex"`` (ALEX-2CDE).
    file_type : str
        tttrlib container name (e.g. ``"SPC-130"``).
    """

    donor_channels: list[int] = field(default_factory=lambda: [0, 8])
    donor_micro_time_ranges: list[tuple[int, int]] = field(default_factory=lambda: [(0, 32768)])
    acceptor_channels: list[int] = field(default_factory=lambda: [1, 9])
    acceptor_micro_time_ranges: list[tuple[int, int]] = field(default_factory=lambda: [(0, 32768)])
    acceptor_excitation_channels: list[int] = field(default_factory=list)
    acceptor_excitation_micro_time_ranges: list[tuple[int, int]] = field(default_factory=list)
    tau: float = 100e-6
    kernel: str = "laplace"
    variant: str = "fret"
    file_type: str = "SPC-130"


@dataclass
class TwoCdeResult:
    """Result of a 2CDE analysis.

    Attributes
    ----------
    files : list of str
        Original TTTR file paths.
    n_bursts_total : int
        Total number of bursts processed.
    n_bursts_valid : int
        Bursts with a finite 2CDE value.
    output_paths : dict
        Paths written by the analysis.
    settings_applied : dict
        The settings that were used.
    """

    files: list[str]
    n_bursts_total: int = 0
    n_bursts_valid: int = 0
    output_paths: dict[str, str] = field(default_factory=dict)
    settings_applied: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
