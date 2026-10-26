"""Experiments whose data stays in a file the workspace links: photons, burst runs, images, setups.

These are experiments like TCSPC or FCS -- declared in ``experiment_configs.yaml``, listed in the
Datasets workspace's *Experiment* column, kept with a project -- but they read nothing into memory
and take no fit model. Each reader turns an address (a file, or a member of a container) into a
:class:`~chisurf.core.data.LinkedDataset` of its kind, linked (size + sha256) through
:mod:`chisurf.core.project.links`:

* :class:`PhotonStreamReader` -- *Single photon counting* (kind ``photons``): a vendor TTTR file or a
  photon stream of a measurement container;
* :class:`BurstRunReader` -- also *Single photon counting* (kind ``bursts``): a burst run is a
  result of analysing a photon stream and lives in its container (``m000.pto/<run>``); the
  workspace shows it as a child row of its photon dataset (``result_of``);
* :class:`ImageStackReader` -- *Imaging* (``image``), both representations: a photon image (photon
  events with a position -- a scanning confocal TTTR stream, a photon-counting camera; linked like a
  photon stream, the image built on demand) or an intensity image (a TIFF stack);
  :class:`~chisurf.core.data.ImageDataset` says which;
* :class:`InstrumentSetupReader` -- *Instrument setup* (``setup``): a detector/channel setup, a
  look-up table, a kinetic scheme, an IRF or background pattern -- what a tool reads besides the
  measurement.

:func:`reader_for_kind` is how the workspace's one drop (:mod:`chisurf.core.fio.classify`) finds
the reader of what it sorted, and :func:`experiment_for_kind` how a restored project gives a linked
dataset its experiment back.
"""

from __future__ import annotations

from typing import Any

import chisurf.core.data
from chisurf.core.experiments.core.reader import ExperimentReader

__all__ = [
    "BurstRunReader",
    "ImageStackReader",
    "InstrumentSetupReader",
    "KIND_EXPERIMENT",
    "LinkedDataReader",
    "PhotonStreamReader",
    "experiment_for_kind",
    "reader_for_kind",
]

#: The experiment (its section in ``experiment_configs.yaml``) that reads each linked kind.
KIND_EXPERIMENT: dict[str, str] = {
    "photons": "photon_counting",
    "bursts": "photon_counting",
    "image": "imaging",
    "setup": "instrument_setup",
}


class LinkedDataReader(ExperimentReader):
    """Read an address into a linked dataset of :attr:`data_kind` -- the file is never loaded."""

    operation_type = "import"
    artifact_kind_source = "external_file"
    #: The kind of what this reader makes (:mod:`chisurf.core.data_kinds`).
    data_kind = ""

    def __init__(self, *args, filename: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self.filename = str(filename or "")

    def make_dataset(self, address: str, link: dict | None = None) -> chisurf.core.data.LinkedDataset:
        """The linked dataset of *address* (*link*: its link record when already hashed)."""
        return chisurf.core.data.LinkedDataset(str(address), data_kind=self.data_kind, link=link)

    def read(self, filename: str | None = None, *args, link: dict | None = None, **kwargs):
        """Return a one-element group holding the linked dataset of *filename* (or the selection)."""
        address = str(filename if filename is not None else self.filename)
        if not address:
            raise ValueError(f"{type(self).__name__} needs an address to link")
        dataset = self.make_dataset(address, link=link)
        dataset.data_reader = self
        group = chisurf.core.data.ExperimentDataGroup(seq=[dataset])
        group.data_reader = self
        self.filename = address
        return group

    @staticmethod
    def autofitrange(data: Any, **kwargs) -> tuple[int, int]:
        """Not fitted: no range."""
        return 0, 0


class PhotonStreamReader(LinkedDataReader):
    """*Single photon counting*: a TTTR file or a container's photon stream, linked, header read once."""

    data_kind = "photons"

    def make_dataset(self, address: str, link: dict | None = None) -> chisurf.core.data.LinkedDataset:
        return chisurf.core.data.PhotonStreamDataset.from_address(str(address), link=link)


class BurstRunReader(LinkedDataReader):
    """A burst run of a measurement container (``m000.pto/<run>``), a result of its photon stream."""

    data_kind = "bursts"

    def make_dataset(
        self, address: str, link: dict | None = None, result_of: str = ""
    ) -> chisurf.core.data.LinkedDataset:
        return chisurf.core.data.LinkedDataset(
            str(address), data_kind="bursts", link=link, result_of=result_of
        )


class ImageStackReader(LinkedDataReader):
    """*Imaging*: a photon image or an intensity image; the representation is detected."""

    data_kind = "image"

    def make_dataset(self, address: str, link: dict | None = None) -> chisurf.core.data.LinkedDataset:
        return chisurf.core.data.ImageDataset.from_address(str(address), link=link)


class InstrumentSetupReader(LinkedDataReader):
    """*Instrument setup*: a detector/channel setup, LUT, kinetic scheme, IRF or background pattern."""

    data_kind = "setup"


def experiment_for_kind(kind: str) -> Any:
    """The registered experiment that reads *kind* (``None`` when the kind has none)."""
    import chisurf as cs
    from chisurf.core.experiments import types

    key = KIND_EXPERIMENT.get(str(kind or ""))
    if key is None:
        return None
    experiment = types.get(key)
    if experiment is None or not getattr(experiment, "readers", None):
        # declared (experiment_types) but its readers not yet attached: register them
        from chisurf.core.experiments.bootstrap import ensure_experiments_registered

        ensure_experiments_registered()
        experiment = types.get(key)
        if experiment is None or not getattr(experiment, "readers", None):
            experiment = cs.experiment.get(key, experiment)
    return experiment


def reader_for_kind(kind: str) -> LinkedDataReader | None:
    """The reader of the experiment that reads *kind* (``None`` when there is none)."""
    experiment = experiment_for_kind(kind)
    for reader in getattr(experiment, "readers", None) or []:
        if isinstance(reader, LinkedDataReader) and reader.data_kind == kind:
            return reader
    return None

