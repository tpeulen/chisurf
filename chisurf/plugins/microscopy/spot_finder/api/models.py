"""Transport dataclasses for spot detection (no Qt).

The detection settings live in the Qt-free core
(:class:`~..core.spots.SpotFinderSettings`); this module re-exports them and
adds the request/result envelopes the CLI and the RPC backend share.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.spots import SpotFinderSettings

__all__ = ["SpotFinderSettings", "SpotFinderRequest", "SpotFinderRunResult", "RunRow"]


@dataclass
class SpotFinderRequest:
    """A detection request over one or more images.

    Parameters
    ----------
    files : list of str
        Images to detect in — TIFF stacks or TTTR imaging files.
    name : str, optional
        Stem the raster/table pair is written under, per file.
    channels : list of int, optional
        Routing channels, for photon files. Every channel present by default.
    frame : int, optional
        Frame to detect in; ``-1`` sums over frames.
    settings : SpotFinderSettings, optional
        Detection settings, shared by every file in the request.
    write : bool, optional
        Write each detection into its measurement's container. Off makes this a
        dry run — useful for tuning against the region count before anything
        lands on disk.
    out_dir : str, optional
        Directory for the containers; beside each file by default.
    """

    files: list[str]
    name: str = "spots"
    channels: list[int] | None = None
    frame: int = -1
    settings: SpotFinderSettings = field(default_factory=SpotFinderSettings)
    write: bool = True
    out_dir: str = ""


@dataclass
class RunRow:
    """What became of one input.

    One of these exists for **every** input, whatever happened to it. A file
    that raised is a row and a file with no spots in it is a row saying zero;
    dropping either is how a batch silently returns a shorter answer than the
    question it was asked.

    Attributes
    ----------
    input : str
        The file.
    status : str
        ``ok``, ``empty``, ``failed`` or ``skipped``.
    n_regions : int
        Regions detected.
    container : str
        Where the pair was written, when it was.
    reason : str
        Why, for anything that is not ``ok``.
    """

    input: str
    status: str
    n_regions: int = 0
    container: str = ""
    reason: str = ""


@dataclass
class SpotFinderRunResult:
    """Result of a detection run over a list of files.

    Attributes
    ----------
    rows : list of RunRow
        One per input, in input order. ``len(rows) == len(request.files)``.
    n_regions : int
        Total regions detected across every file.
    """

    rows: list[RunRow] = field(default_factory=list)
    n_regions: int = 0

    @property
    def ok(self) -> list[RunRow]:
        """Rows that produced regions."""
        return [row for row in self.rows if row.status == "ok"]

    @property
    def failed(self) -> list[RunRow]:
        """Rows that did not."""
        return [row for row in self.rows if row.status not in ("ok", "empty")]
