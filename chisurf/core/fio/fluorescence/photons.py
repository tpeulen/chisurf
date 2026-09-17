"""Read TTTR files into a photon stream.

TTTR files contain time-tagged-time-resolved records typically recorded in
single-molecule experiments and on confocal laser scanning setups.

:class:`Photons` is a thin, sliceable wrapper around a ``tttrlib.TTTR``
object. Reading goes through :func:`chisurf.core.fio.staging.open_tttr`, the
single seam that also stages slow files locally and applies per-channel TAC
linearization; :attr:`Photons.tttr` hands the underlying object to anything
that wants to use ``tttrlib`` directly (the correlator does).

Historically this module converted every supported format into a bespoke
Photon-HDF5 file -- one PyTables table per measurement, written to a scratch
file -- and read the photons back out of it, with per-format record parsers of
its own. That is gone: it cost a temporary copy of every measurement on disk,
kept an HDF5 file open for the life of the process, and duplicated format
support ``tttrlib`` already has.
"""

from __future__ import annotations

import numpy as np

from chisurf import typing

#: Names the per-photon arrays are known by inside a selection expression.
#: Kept from the Photon-HDF5 column names, so an expression written against the
#: old table still evaluates.
COLUMN_NAMES = ("MT", "TAC", "ROUT", "EVENT")


def read_burst_ids(filenames: typing.List[str], stack_files: bool = True) -> np.array:
    """
    Reads Seidel-BID files and returns a list of numpy
    arrays. Each numpy array contains the indexes of
    the photons of the burst. These indexes can be used
    to slice a photon-stream.

    Seidel BID-files only contain the first and the
    last photon of the Burst and not all photons of
    the burst. Thus, the Seidel BID-files have to be
    converted to array-type objects containing all
    photons of the burst to be able to use standard
    Python slicing syntax to select photons.

    :param filenames:
        filename pointing to a Seidel BID-file
    :param stack_files: bool
        If stack is True the returned list is stacked
        and the numbering of the bursts is made continuous.
        This is the default behavior.
    :return:

    Examples
    --------
    >>> import glob  # doctest: +SKIP
    >>> bids = read_burst_ids(glob.glob("./BID/*.bst"))  # doctest: +SKIP
    """
    if isinstance(filenames, str):
        filenames = [filenames]
    re = dict()
    for file in filenames:
        bids = np.loadtxt(file, dtype=np.int32)
        re[file] = [np.arange(bid[0], bid[1], dtype=np.int32) for bid in bids]
    if not stack_files:
        return re
    else:
        b = re[filenames[0]]
        if len(filenames) > 1:
            for i, fn in enumerate(filenames[1:]):
                offset = re[filenames[i]][-1][-1]
                for j in range(len(re[fn])):
                    b.append(re[fn][j] + offset)
        return b


class Photons:
    """A photon stream read from one or more TTTR files.

    Parameters
    ----------
    p_object : str, list of str, tttrlib.TTTR, or None
        Files to read, an already-read ``tttrlib.TTTR`` to wrap, or ``None``
        for an empty stream. Several files are read in sorted order with their
        macro times made continuous, so a measurement split over several files
        behaves as one acquisition.
    reading_routine : str, optional
        Container type. Leave it unset unless the format is genuinely
        ambiguous (SPC-130 against SPC-600): ``tttrlib`` identifies the
        container from the file, and a type guessed from a file extension gets
        it wrong.
    verbose : bool, optional
        Accepted and ignored; kept so existing call sites keep working.

    Examples
    --------
    >>> from chisurf.core.fio.fluorescence.photons import Photons  # doctest: +SKIP
    >>> p = Photons('BH_SPC132.spc')  # doctest: +SKIP
    >>> p.nPh  # doctest: +SKIP
    183657
    >>> len(p[:10])  # doctest: +SKIP
    10
    """

    def __init__(self, p_object=None, reading_routine: str = None, verbose: bool = None):
        """Read the given files, wrap a TTTR object, or build an empty stream."""
        import tttrlib

        self.filetype = reading_routine
        self.verbose = verbose
        self._filenames: typing.List[str] = []
        self._tttr = None

        if p_object is None:
            return
        if isinstance(p_object, tttrlib.TTTR):
            self._tttr = p_object
            return
        if isinstance(p_object, str):
            self._filenames = [p_object]
        else:
            self._filenames = sorted(p_object)
        if self._filenames:
            self._tttr = self._read(self._filenames, reading_routine)

    @staticmethod
    def _read(filenames, reading_routine):
        """Read every file into one continuous stream.

        The macro times of the second and later files are shifted past the end
        of the previous one, so a measurement recorded in several files
        correlates as a single acquisition rather than as one that keeps
        jumping back in time.

        Parameters
        ----------
        filenames : list of str
            Files to read, already sorted.
        reading_routine : str or None
            Container type to hand to ``tttrlib``.

        Returns
        -------
        tttrlib.TTTR
            The combined stream.
        """
        from chisurf.core.fio.staging import open_tttr

        stream = None
        for filename in filenames:
            part = open_tttr(filename, reading_routine)
            if stream is None:
                stream = part
            else:
                stream.append(part, shift_macro_time=True)
        return stream

    @property
    def tttr(self):
        """The underlying ``tttrlib.TTTR`` object, or ``None`` when empty."""
        return self._tttr

    def close(self) -> None:
        """Drop the photon data.

        A read leaves no file open -- ``tttrlib`` hands the events over in
        memory -- so this only releases the reference. It exists so that a
        caller owning a reader can say when it is done with it.
        """
        self._tttr = None

    def __enter__(self) -> Photons:
        """Return self, so a reader can be used as a context manager."""
        return self

    def __exit__(self, *exc_info) -> None:
        """Drop the photon data on leaving the ``with`` block."""
        self.close()

    def _array(self, name: str, dtype) -> np.ndarray:
        """Return one of the per-photon arrays, empty when nothing is loaded.

        Parameters
        ----------
        name : str
            Attribute of the ``tttrlib.TTTR`` object to read.
        dtype : np.dtype
            Type of the empty array returned for an empty stream.

        Returns
        -------
        np.ndarray
            The requested per-photon array.
        """
        if self._tttr is None:
            return np.zeros(0, dtype=dtype)
        return np.asarray(getattr(self._tttr, name))

    @property
    def filenames(self) -> typing.List[str]:
        """Files this stream was read from."""
        return self._filenames

    @property
    def measurement_time(self) -> float:
        """Duration of the measurement, in seconds."""
        times = self.macro_times
        return float(times[-1]) * self.mt_clk if times.size else 0.0

    @property
    def dt(self) -> float:
        """Micro-time calibration: the width of one TAC channel, in seconds."""
        return self.mt_clk / self.n_tac if self.n_tac else 0.0

    @property
    def shape(self) -> typing.Tuple[int]:
        """Shape of the photon data (number of photons,)."""
        return self.routing_channels.shape

    @property
    def nPh(self) -> int:
        """Number of photons in the stream."""
        return 0 if self._tttr is None else int(len(self._tttr))

    @property
    def routing_channels(self) -> np.ndarray:
        """Routing (detection) channel of every photon."""
        return self._array("routing_channels", np.int8)

    @property
    def micro_times(self) -> np.ndarray:
        """Micro time (TAC channel) of every photon."""
        return self._array("micro_times", np.uint32)

    @property
    def event_types(self) -> np.ndarray:
        """Event type of every photon."""
        return self._array("event_types", np.int8)

    @property
    def macro_times(self) -> np.ndarray:
        """Macro time of every photon, in macro-time clock counts."""
        return self._array("macro_times", np.uint64)

    @property
    def n_tac(self) -> int:
        """Number of TAC (micro time) channels of the measurement."""
        if self._tttr is None:
            return 0
        return int(self._tttr.header.number_of_micro_time_channels)

    @property
    def mt_clk(self) -> float:
        """Macro-time clock: the time between macro-time counts, in seconds."""
        if self._tttr is None:
            return 0.0
        return float(self._tttr.header.macro_time_resolution)

    def by_channel(self, channels) -> Photons:
        """Return the photons detected in the given routing channels.

        Parameters
        ----------
        channels : sequence of int
            Routing channels to keep.

        Returns
        -------
        Photons
            A stream over those photons.
        """
        if self._tttr is None:
            return Photons(None)
        selection = self._tttr.get_selection_by_channel(list(channels))
        return self.take(selection)

    def where(self, expression: str) -> np.ndarray:
        """Return the indices of the photons a selection expression matches.

        The expression is written in terms of :data:`COLUMN_NAMES` -- for
        instance ``"(ROUT == 0) & (TAC > 100)"`` -- which are the names the
        Photon-HDF5 table used, so an expression a user saved against it still
        works.

        Parameters
        ----------
        expression : str
            Boolean expression over ``MT``, ``TAC``, ``ROUT`` and ``EVENT``.

        Returns
        -------
        np.ndarray
            Indices of the matching photons.

        Raises
        ------
        ValueError
            If the expression cannot be evaluated over the photon arrays.
        """
        columns = {
            "MT": self.macro_times,
            "TAC": self.micro_times,
            "ROUT": self.routing_channels,
            "EVENT": self.event_types,
        }
        try:
            mask = eval(expression, {"__builtins__": {}}, columns)  # noqa: S307
        except Exception as exception:
            raise ValueError(
                f"cannot evaluate the photon selection {expression!r}: {exception}"
            ) from exception
        return np.flatnonzero(np.asarray(mask))

    def take(self, keys) -> Photons:
        """Return a stream over the given photon indices.

        Parameters
        ----------
        keys : ndarray
            Indices to select.

        Returns
        -------
        Photons
            New stream over the selected photons.
        """
        if self._tttr is None:
            return Photons(None)
        keys = np.asarray(keys, dtype=np.int64)
        selected = Photons(self._tttr[keys], reading_routine=self.filetype)
        selected._filenames = self._filenames
        return selected

    def __str__(self):
        """Return a string summary of the photon stream."""
        s = ""
        s += f"File-type: {self.filetype}\n"
        s += "Filename(s):\t"
        if len(self.filenames) > 0:
            s += "\n"
            for fn in self.filenames:
                s += "\t" + fn + "\n"
        else:
            s += "None\n"
        s += "nTAC:\t%d\n" % self.n_tac
        s += f"MTCLK [s]:\t{self.mt_clk}\n"
        return s

    def __len__(self):
        """Number of photons."""
        return self.nPh

    def __getitem__(self, key):
        """Return a stream over the selected photons.

        Parameters
        ----------
        key : int, slice or ndarray
            Photons to select.

        Returns
        -------
        Photons
            New stream with the selection.
        """
        if isinstance(key, (int, np.integer)):
            keys = np.array([key])
        elif isinstance(key, slice):
            keys = np.arange(*key.indices(len(self)))
        else:
            keys = np.asarray(key)
        return self.take(keys=keys)
