"""What kind of data a dataset is: one small vocabulary the workspace, the API and the plugins share.

A dataset's *experiment* says what it was read for (TCSPC, FCS, PDA, ...); its *kind* says what it is —
a decay, a correlation curve, a histogram, a photon stream — which is what the Datasets workspace filters
by and what a plugin declares it takes. Curves get their kind from their experiment; a dataset class that
is a kind of its own says so with a ``data_kind`` class attribute (a photon stream, a structure).

Every experiment the tree registers is listed in :data:`EXPERIMENT_KINDS`; an experiment that is not is
reported, never silently given a kind (``test/core/test_data_kinds.py`` checks the list against the
registered experiments).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "EXPERIMENT_KINDS",
    "KINDS",
    "Kind",
    "is_fittable",
    "kind_of",
    "kind_of_experiment",
    "kind_options",
]


@dataclass(frozen=True)
class Kind:
    """One kind of data: its key, how the workspace names it, and whether a fit can take it."""

    key: str
    label: str
    plural: str
    icon: str
    fittable: bool
    description: str


#: The vocabulary, in the order the workspace filter lists it.
KINDS: dict[str, Kind] = {
    k.key: k
    for k in (
        Kind(
            "photons",
            "Photons",
            "Photons",
            "✨",
            False,
            "A single-photon (TTTR) stream: every photon's arrival time and channel.",
        ),
        Kind(
            "decay",
            "Decay",
            "Decays",
            "📉",
            True,
            "A fluorescence decay: photon counts over the micro time (TCSPC).",
        ),
        Kind(
            "correlation",
            "Correlation",
            "Correlations",
            "🔗",
            True,
            "A correlation curve: FCS, pair or image correlation.",
        ),
        Kind(
            "histogram",
            "Histogram",
            "Histograms",
            "📊",
            True,
            "A histogram of a measured quantity: PDA, PCH or a multiparameter (MFD) histogram.",
        ),
        Kind(
            "trace",
            "Trace",
            "Traces",
            "📈",
            True,
            "A signal over time: a DEER dipolar evolution or a stopped-flow kinetic trace.",
        ),
        Kind(
            "bursts",
            "Bursts",
            "Bursts",
            "💥",
            False,
            "A burst run of a measurement container: one row per selected burst.",
        ),
        Kind(
            "structure",
            "Structure",
            "Structures",
            "🧬",
            True,
            "A molecular structure (the Modelling experiment fits it).",
        ),
        Kind("image", "Image", "Images", "🖼️", False, "An image or a confocal scan."),
    )
}

#: Every experiment the tree registers, by its display name, and the kind its curves are. ``None`` is a
#: deliberate "no kind": the hidden *Global* experiment holds the groups of a global fit, not data.
EXPERIMENT_KINDS: dict[str, str | None] = {
    "TCSPC": "decay",
    "FCS": "correlation",
    "PCF": "correlation",
    "Image correlation": "correlation",
    "PCH": "histogram",
    "PDA": "histogram",
    "MFD": "histogram",
    "DEER": "trace",
    "Stopped flow": "trace",
    "Modelling": "structure",
    "Global": None,
}

_reported: set[str] = set()


def kind_of_experiment(name: str) -> str | None:
    """The kind of a curve read for the experiment *name*; ``None`` for no kind (or an unlisted one).

    An experiment that is not in :data:`EXPERIMENT_KINDS` is logged once: it needs an entry, not a guess.
    """
    name = str(name or "")
    if name in EXPERIMENT_KINDS:
        return EXPERIMENT_KINDS[name]
    if name and name not in _reported:
        _reported.add(name)
        logger.warning("experiment %r has no data kind; add it to chisurf.core.data_kinds", name)
    return None


def kind_of(dataset: Any) -> str | None:
    """The kind of *dataset*: its class's ``data_kind`` when it has one, else its experiment's."""
    declared = getattr(type(dataset), "data_kind", None) or getattr(dataset, "data_kind", None)
    if declared:
        return str(declared)
    try:
        from chisurf.core.structure import Structure

        if isinstance(dataset, Structure):
            return "structure"
    except ImportError:  # pragma: no cover - the structure layer always ships
        pass
    experiment = getattr(getattr(dataset, "experiment", None), "name", "")
    return kind_of_experiment(str(experiment or ""))


def is_fittable(kind: str | None) -> bool:
    """Whether a fit can take data of *kind*; an unknown (``None``) kind is not refused."""
    if kind is None:
        return True
    found = KINDS.get(kind)
    return True if found is None else found.fittable


def kind_options(present: Any = None) -> list[tuple[str, str]]:
    """``(value, label)`` pairs for a kind filter: *All*, then each kind in *present* (all when ``None``)."""
    wanted = None if present is None else {str(k) for k in present if k}
    options = [("", "All kinds")]
    for key, kind in KINDS.items():
        if wanted is None or key in wanted:
            options.append((key, f"{kind.icon} {kind.plural}"))
    return options
