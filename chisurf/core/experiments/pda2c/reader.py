"""Photon distribution analysis (PDA) experiment utilities.

This module provides helper functions and the :class:`Pda2cReader` used
to construct PDA histograms from time-tagged single-photon (TTTR) data.

The central pieces are:

* :func:`build_idx_map` – vectorized helper that expands per-file
  index intervals into NumPy index arrays.
* :class:`Pda2cReader` – experiment reader that uses :mod:`tttrlib` to
  compute experimental S1S2 histograms and attach PDA metadata to
  :class:`chisurf.core.data.DataCurve` objects.

The examples in this module avoid touching real TTTR files; all
heavy I/O and :mod:`tttrlib` calls are only shown in skipped doctests.
"""

from __future__ import annotations

import json
import pathlib
from typing import Dict, Sequence, Tuple

import numpy as np
import tttrlib

import chisurf.core.base
import chisurf.core.curve
import chisurf.core.data
import chisurf.core.fio.fluorescence
import chisurf.core.fluorescence
import chisurf.core.fluorescence.tcspc
import chisurf.core.settings
from chisurf import logging, typing
from chisurf.core.experiments.core.reader import ExperimentReader

from .index_map import build_idx_map

_VIEW_JSON = pathlib.Path(__file__).parent / "pda.view.json"


class Pda2cReader(ExperimentReader):
    operation_type = "pda_histogram_computation"
    artifact_kind_source = "raw_data"
    artifact_kind_derived = "pda_histogram"
    derived_data_format = "json"
    derived_mime_type = "application/json"

    """Experiment reader for PDA TTTR data.

    This reader uses :mod:`tttrlib` to construct experimental S1S2
    histograms from TTTR files and attaches PDA metadata to
    :class:`chisurf.core.data.DataCurve` objects.

    Parameters
    ----------
    channels : tuple of list of int
        Channel numbers for donor/acceptor detection (green, red).
    micro_time_ranges : list of (int, int)
        Micro-time windows used for photon selection.
    reading_routine : str, optional
        :mod:`tttrlib` reader type (e.g. ``'PTU'``, default).
    maximum_number_of_photons : int, optional
        Maximum photon number used for the S1S2 histogram support.
    minimum_number_of_photons : int, optional
        Minimum total photon number for bursts.
    minimum_time_window_length : float, optional
        Minimum time window length for bursts in seconds.

    Notes
    -----
    The :meth:`read` method performs real file I/O and depends on
    :mod:`tttrlib`. A minimal usage pattern (omitting real files) is::

        >>> from chisurf.core.experiments.pda2c import Pda2cReader  # doctest: +SKIP
        >>> r = Pda2cReader(  # doctest: +SKIP
        ...     channels=([0], [1]),
        ...     micro_time_ranges=[(0, 4096)],
        ...     reading_routine='PTU'
        ... )  # doctest: +SKIP
    """

    def __init__(
            self,
            channels: typing.Tuple[typing.List[int], typing.List[int]],
            micro_time_ranges: typing.List[typing.Tuple[int, int]],
            reading_routine: str = 'PTU',
            maximum_number_of_photons: int = 500,
            minimum_number_of_photons: int = 5,
            minimum_time_window_length: float = 2e-3,
            tw_configs=None,
            n_colors: int = None,
            segmentation: str = "burst",
            *args,
            **kwargs
    ):
        """Initialize a PDA reader.

        Parameters
        ----------
        channels : tuple of list of int
            Detection channel numbers. Two entries ``(green, red)`` for
            two-colour PDA; three ``(blue, green, red)`` for three-colour.
        micro_time_ranges : list of tuple of int
            Micro-time windows ``(start, stop)`` for photon selection. For
            three colours these are the **excitation periods** — the blue and
            green halves of the PIE cycle.
        reading_routine : str
            tttrlib reader type (e.g. ``'PTU'``).
        maximum_number_of_photons : int
            Maximum photon number for the S1S2 histogram support.
        minimum_number_of_photons : int
            Minimum total photon count per burst.
        minimum_time_window_length : float
            Minimum time window length for bursts in seconds.
        tw_configs : list, optional
            List of ``(min_photons, min_tw_len_s)`` configurations.
        n_colors : int, optional
            Number of colours, 2 or 3. Defaults to the number of channel
            groups, so a three-colour detection setup produces three-colour
            data without being told twice.
        segmentation : str
            How the photon stream is cut into observations.

            ``"burst"`` (default) runs a burst search: windows are found where
            the photon flux is high enough, so their durations *vary* and
            ``minimum_time_window_length`` is a lower bound rather than the
            observation time.

            ``"time-bins"`` cuts the whole stream into consecutive windows of
            **exactly** ``minimum_time_window_length``, keeping those within the
            photon-count limits. This is the segmentation classic PDA assumes,
            and the one a dynamic model needs: exchange enters through the
            number of transitions per observation, so the observation time has
            to be a known constant rather than a distribution. Reading the same
            file at several bin widths and fitting them together is what turns
            the dimensionless exchange parameter into an absolute rate.
        """
        super().__init__(*args, **kwargs)
        self.reading_routine = reading_routine
        self.micro_time_ranges = micro_time_ranges
        self.maximum_number_of_photons = maximum_number_of_photons
        self.minimum_number_of_photons = minimum_number_of_photons
        self.minimum_time_window_length = minimum_time_window_length
        self.tw_configs = tw_configs
        self.channels = channels
        self.n_colors = int(n_colors) if n_colors else len(channels)
        self.segmentation = str(segmentation)

    # -- three-colour path ------------------------------------------------

    def _micro_time_range(self, index: int) -> tuple:
        """Return micro-time window ``index``, falling back to the first."""
        ranges = list(self.micro_time_ranges or [(0, 2 ** 31)])
        return tuple(ranges[min(index, len(ranges) - 1)])

    def detection_windows(self) -> list:
        """Return the ``(channels, micro_time_range)`` pairs a burst is counted in.

        One entry per physical excitation/detection combination, which is what
        makes the two colour counts the same kind of object rather than two
        code paths:

        - **two colours** — green and red detection, each with its own
          photon-selection window;
        - **three colours** — five combinations, because the blue pulse can be
          seen in all three detectors while the green pulse is only visible in
          green and red (nothing emits blue after a green excitation).

        Returns
        -------
        list of (list of int, tuple of int)
            Two-colour order ``(green, red)``; three-colour order
            ``F_BB, F_BG, F_BR, F_GG, F_GR``.
        """
        if int(getattr(self, "n_colors", 2)) >= 3:
            blue_excitation = self._micro_time_range(0)
            green_excitation = self._micro_time_range(1)
            blue, green, red = (list(c) for c in self.channels[:3])
            return [
                (blue, blue_excitation),
                (green, blue_excitation),
                (red, blue_excitation),
                (green, green_excitation),
                (red, green_excitation),
            ]
        return [
            (list(channels), self._micro_time_range(index))
            for index, channels in enumerate(self.channels[:2])
        ]

    def _three_color_curve(self, blue, green, name, filename,
                           minimum_number_of_photons, minimum_time_window_length,
                           tttr_header_json=None, source_filenames=None):
        """Wrap a three-colour burst table into a DataCurve the PDA3c model reads.

        The curve's ``y`` is the measured proximity-ratio histograms, so the
        ordinary plotting machinery works; the payload the model actually fits
        rides in ``meta_data['pda3c']``.
        """
        from chisurf.core.fluorescence.pda3c import BurstCounts
        from chisurf.core.models.pda3c.pda3c import observed_ratio_histograms

        counts = BurstCounts(blue=blue, green=green)
        histogram = observed_ratio_histograms(counts.collapsed()) * max(blue.shape[0], 1)
        y = np.asarray(histogram, dtype=float)
        x = np.arange(y.size, dtype=float)

        payload = {
            "blue": np.asarray(blue, dtype=float),
            "green": np.asarray(green, dtype=float),
            "n_bursts": int(blue.shape[0]),
            "columns": ["F_BB", "F_BG", "F_BR", "F_GG", "F_GR"],
            "channels": self.channels,
            "micro_time_ranges": self.micro_time_ranges,
            "minimum_number_of_photons": int(minimum_number_of_photons),
            "minimum_time_window_length": float(minimum_time_window_length),
        }
        meta_all = {
            "pda3c": payload,
            "tttr_header_json": tttr_header_json,
            "filenames": source_filenames,
            "reading_routine": self.reading_routine,
            "micro_time_ranges": self.micro_time_ranges,
        }
        data = chisurf.core.data.DataCurve(
            name=name,
            filename=filename,
            load_filename_on_init=False,
            data_reader=self,
            meta_data=meta_all,
            y=y, x=x,
            ey=chisurf.core.fluorescence.tcspc.counting_noise(y),
        )
        data.pda3c = payload
        return data

    def burst_count_table(self, tttr_data, minimum_number_of_photons: int,
                          minimum_time_window_length: float):
        """Return per-burst photon counts for the three-colour model.

        Bursts are the time windows ``get_ranges_by_time_window`` finds, using
        the same ``minimum_time_window_length`` / ``minimum_number_of_photons``
        settings as the two-colour path.

        **The two paths do not select identical bursts.** Measured on
        ``test/data/tttr/BH/132/BH_SPC132.spc`` at 2 ms / 20 photons, this
        yields 731 windows while ``Pda.compute_experimental_histograms`` reports
        455 — the engine applies a further internal selection that its API does
        not expose and that a duration or photon-count filter does not
        reproduce. The recovered proximity-ratio *distributions* agree to a
        total variation of ~0.17. So: comparable, not interchangeable. Do not
        read a two- and a three-colour analysis of the same file as having
        identical burst sets.

        Counting is done with a cumulative sum per detection window rather than
        a Python loop over bursts, which keeps a multi-million-photon file
        interactive.

        Parameters
        ----------
        tttr_data : tttrlib.TTTR
            Photon stream.
        minimum_number_of_photons : int
            Minimum photons per time window.
        minimum_time_window_length : float
            Minimum time-window length in seconds.

        Returns
        -------
        numpy.ndarray
            ``(n_bursts, n_detection_windows)`` counts, columns ordered as
            :meth:`detection_windows`.
        """
        ranges = np.asarray(
            tttr_data.get_ranges_by_time_window(
                minimum_time_window_length,
                -1,
                int(minimum_number_of_photons),
                -1,
            ),
            dtype=np.int64,
        )
        windows = self.detection_windows()
        if ranges.size < 2:
            return np.zeros((0, len(windows)))
        ranges = ranges.reshape(-1, 2)
        starts = ranges[:, 0]
        stops = np.minimum(ranges[:, 1], len(tttr_data) - 1)

        routing = np.asarray(tttr_data.routing_channels)
        micro = np.asarray(tttr_data.micro_times)

        counts = np.zeros((starts.size, len(windows)), dtype=float)
        for index, (channels, (low, high)) in enumerate(windows):
            mask = np.isin(routing, channels) & (micro >= low) & (micro <= high)
            cumulative = np.concatenate(([0], np.cumsum(mask, dtype=np.int64)))
            # The ranges are INCLUSIVE of ``stop``: measured on real data, every
            # window spans at least ``minimum_time_window_length`` only when the
            # stop photon is counted, and none of them do when it is dropped.
            # (``fluorescence/burst/bva.py`` slices ``[start:stop]`` and so
            # silently loses the last photon of every burst.)
            counts[:, index] = cumulative[stops + 1] - cumulative[starts]
        return counts

    def time_binned_histograms(self, tttr_data, channels_1, channels_2,
                               window_length: float,
                               minimum_number_of_photons: int,
                               maximum_number_of_photons: int):
        """Return the S1S2 histogram of consecutive fixed-width time bins.

        The segmentation classic PDA is defined on: the whole photon stream is
        cut into abutting windows of *exactly* ``window_length``, and each
        surviving window contributes one ``(S1, S2)`` pair to the histogram. A
        burst search cannot substitute for this in a dynamic analysis — it
        returns windows whose durations vary with the local photon flux, so the
        observation time that exchange is measured against is a distribution
        rather than a number, and the recovered rate absorbs whatever that
        distribution happened to be.

        Empty and under-filled bins are dropped rather than counted at the
        origin: a window with no molecule in it carries no information about
        exchange, and at typical duty cycles they would otherwise dominate.

        Parameters
        ----------
        tttr_data : tttrlib.TTTR
            Photon stream.
        channels_1, channels_2 : list of int
            Routing channels of the two detection colours.
        window_length : float
            Bin width in seconds. This *is* the observation time.
        minimum_number_of_photons, maximum_number_of_photons : int
            Windows outside this total-count range are discarded; the histogram
            support is ``maximum_number_of_photons`` in each channel.

        Returns
        -------
        s1s2 : numpy.ndarray
            ``(n_max + 1, n_max + 1)`` counts, rows channel 1, columns channel 2
            — the orientation the model's matrix uses.
        ps : numpy.ndarray
            Photon-number distribution: the fraction of kept windows with each
            total photon count, which is what the model needs to weight its
            per-``N`` binomials.
        indices : numpy.ndarray
            First photon index of each kept window, for provenance.
        """
        macro = np.asarray(tttr_data.macro_times, dtype=np.float64)
        if macro.size == 0:
            n_max = int(maximum_number_of_photons)
            return (np.zeros((n_max + 1, n_max + 1)), np.zeros(n_max + 1),
                    np.zeros(0, dtype=np.int64))
        resolution = float(tttr_data.header.macro_time_resolution)
        bin_width = float(window_length) / resolution          # in macro-time ticks
        routing = np.asarray(tttr_data.routing_channels)

        # Bin index of every photon. Consecutive and abutting by construction,
        # so no window is missed and none overlaps.
        index = ((macro - macro[0]) / bin_width).astype(np.int64)
        n_bins = int(index[-1]) + 1

        in_1 = np.isin(routing, np.asarray(channels_1))
        in_2 = np.isin(routing, np.asarray(channels_2))
        s1 = np.bincount(index[in_1], minlength=n_bins)
        s2 = np.bincount(index[in_2], minlength=n_bins)

        total = s1 + s2
        n_max = int(maximum_number_of_photons)
        keep = (total >= int(minimum_number_of_photons)) & (total <= n_max)
        s1, s2 = s1[keep], s2[keep]

        s1s2 = np.zeros((n_max + 1, n_max + 1), dtype=float)
        np.add.at(s1s2, (s1, s2), 1.0)

        counts = np.bincount(s1 + s2, minlength=n_max + 1)[: n_max + 1].astype(float)
        ps = counts / counts.sum() if counts.sum() > 0 else counts

        first = np.searchsorted(index, np.flatnonzero(keep))
        return s1s2, ps, first.astype(np.int64)

    def view_spec(self):
        """Return the declarative editor spec for PDA reader settings."""
        from chisurf.core.dataspec import load_view_spec
        return load_view_spec(_VIEW_JSON)

    def autofitrange(self, data, **kwargs) -> typing.Tuple[int, int]:
        """Return the full flattened data range as the default fit interval.

        Parameters
        ----------
        data : chisurf.core.base.Data
            The experimental PDA data.

        Returns
        -------
        tuple of int
            ``(0, len(y))`` for the flattened y data.
        """
        logging.warning("PDA autofitrange not yet implemented")
        return 0, len(data.y.flatten())

    def read(self, filename: typing.List[str] = None, *args, **kwargs) -> chisurf.core.data.ExperimentDataGroup:
        """Read PDA TTTR data and return S1S2 histograms.

        Parameters
        ----------
        filename : list of str, optional
            Path(s) to the TTTR data file(s).

        Returns
        -------
        chisurf.core.data.ExperimentDataGroup
            Group containing :class:`DataCurve` objects with S1S2 histograms.
            Each curve carries the following metadata:

            - ``curve.pda`` — PDA-specific dict with keys:
              ``maximum_number_of_photons``, ``minimum_number_of_photons``,
              ``minimum_time_window_length``, ``channels``, ``s1s2``,
              ``ps``, ``row_indices``, ``col_indices``, ``ndim``, ``shape``,
              ``size``, ``reading_routine``, ``micro_time_ranges``,
              ``tttr_indices``.
            - ``curve.meta_data`` — generic metadata dict with keys:
              ``filenames`` (list of source file paths), ``grid`` (2D grid
              description), ``tttr_header_json`` (TTTR file header JSON
              string), ``tw_configs`` (list of time-window configurations
              used).
        """
        if isinstance(filename, str):
            filename = [filename]

        try:
            logging.info(
                "PDA TRACE: Pda2cReader.read called with %d filename(s)",
                len(filename) if filename is not None else -1,
            )
        except Exception:
            pass

        filename.sort()
        from chisurf.core.file_formats import FILE_FORMATS as _FILE_FORMATS
        source_filenames = [
            {
                'path': str(p),
                'format': _FILE_FORMATS.get(p.suffix.lower(), {}).get('name', ''),
            }
            for p in (pathlib.Path(f) for f in filename)
            if p.is_file()
        ]
        fn = pathlib.Path(source_filenames[0]['path']) if source_filenames else pathlib.Path(filename[0])
        data_group = chisurf.core.data.ExperimentDataGroup([])

        # Optional burst slicing: dict[str, List[Tuple[int,int]]]
        burst_slices = kwargs.get('burst_slices', None)
        if isinstance(burst_slices, dict) and len(burst_slices) == 0:
            burst_slices = None

        logging.debug({
            'reader': 'Pda2cReader',
            'reading_routine': self.reading_routine,
            'n_input_files': len(filename),
            'first_file': str(fn)
        })

        t = None
        if fn.is_file():
            if burst_slices:
                # Build a TTTR consisting only of specified intervals using vectorized indices
                logging.info(f"PDA.read: Applying burst_slices to TTTR data for {len(filename)} file(s) using index maps.")
                try:
                    logging.info(
                        "PDA TRACE: burst_slices mode enabled with %d key(s)",
                        len(burst_slices) if burst_slices is not None else 0,
                    )
                except Exception:
                    pass
                # Prepare intervals per actually provided filenames (match keys by full path, name, or stem)
                intervals_by_file: Dict[str, Sequence[Tuple[int, int]]] = {}
                # Normalize keys in a helper for quick access
                def _get_intervals_for_path(p: pathlib.Path):
                    """Return burst-slice intervals for a file path.

                    Tries lookups by full path, basename, and stem.

                    Parameters
                    ----------
                    p : pathlib.Path
                        The file path to look up.

                    Returns
                    -------
                    list
                        The matching burst intervals, or an empty list.
                    """
                    return (
                        burst_slices.get(str(p), [])
                        or burst_slices.get(p.name, [])
                        or burst_slices.get(p.stem, [])
                    )
                for f in filename:
                    pf = pathlib.Path(f)
                    if not pf.is_file():
                        continue
                    ivals = _get_intervals_for_path(pf)
                    if ivals:
                        intervals_by_file[str(pf)] = ivals
                try:
                    logging.info(
                        "PDA TRACE: intervals_by_file built for %d file(s)",
                        len(intervals_by_file),
                    )
                except Exception:
                    pass
                if not intervals_by_file:
                    t = None
                else:
                    # Build indices; our intervals are [start, stop) so inclusive_stop=False
                    try:
                        logging.info(
                            "PDA TRACE: calling build_idx_map for %d file(s)",
                            len(intervals_by_file),
                        )
                    except Exception:
                        pass
                    idx_map = build_idx_map(intervals_by_file, inclusive_stop=False, dtype=np.int64)
                    try:
                        logging.info(
                            "PDA TRACE: build_idx_map finished; idx_map has %d key(s)",
                            len(idx_map),
                        )
                    except Exception:
                        pass
                    t_sel = None
                    for f in filename:
                        pf = pathlib.Path(f)
                        if not pf.is_file():
                            continue
                        key = str(pf)
                        idxs = idx_map.get(key)
                        if idxs is None or idxs.size == 0:
                            continue
                        try:
                            try:
                                logging.info(
                                    "PDA TRACE: loading TTTR with burst slices: %s (n_indices=%d)",
                                    key,
                                    int(idxs.size),
                                )
                            except Exception:
                                pass
                            tt = self._open_tttr(pf.as_posix(), self.reading_routine)
                            # Use vectorized selection once per file
                            ds = tt[idxs]
                        except Exception:
                            continue
                        if ds is None:
                            continue
                        if t_sel is None:
                            t_sel = ds
                        else:
                            t_sel.append(ds)
                    t = t_sel
            else:
                # Default: load entire files and append
                try:
                    logging.info(
                        "PDA TRACE: loading full TTTR data for %d file(s)",
                        len(filename),
                    )
                except Exception:
                    pass
                t = self._open_tttr(fn.as_posix(), self.reading_routine)
                for fn in filename[1:]:
                    fn = pathlib.Path(fn)
                    if fn.is_file():
                        try:
                            logging.info("PDA TRACE: appending TTTR file %s", str(fn))
                        except Exception:
                            pass
                        d = self._open_tttr(fn.as_posix(), self.reading_routine)
                        t.append(d)

        if t is not None:
            # Passthrough TTTR metadata: extract header JSON once for reuse
            # across all time-window configurations.
            tttr_header_json = None
            try:
                tttr_header_json = t.get_header().get_json()
            except Exception:
                pass

            channels_1 = self.channels[0]
            channels_2 = self.channels[1]

            # Determine the list of (minimum_number_of_photons, minimum_time_window_length)
            # configurations to run. If no explicit list was provided, fall back to the
            # single reader-level thresholds for backward compatibility.
            configs = []
            tw_cfgs = getattr(self, 'tw_configs', None)
            if tw_cfgs:
                for cfg in tw_cfgs:
                    try:
                        n_ph, tw_len = int(cfg[0]), float(cfg[1])
                    except Exception:
                        continue
                    if n_ph <= 0 or tw_len <= 0.0:
                        continue
                    configs.append((n_ph, tw_len))
            if not configs:
                try:
                    configs = [
                        (
                            int(self.minimum_number_of_photons),
                            float(self.minimum_time_window_length),
                        )
                    ]
                except Exception:
                    configs = []

            base_name = fn.stem
            multi = len(configs) > 1

            if int(getattr(self, "n_colors", 2)) >= 3:
                # Three-colour setups take the burst-table path: PDA3c fits a
                # per-burst photon partition, not an S1S2 histogram, so there is
                # nothing to build a 2D grid from. Same file reading, same burst
                # definition, different payload.
                for n_ph_cfg, tw_len_cfg in configs:
                    table = self.burst_count_table(t, n_ph_cfg, tw_len_cfg)
                    blue, green = table[:, :3], table[:, 3:]
                    name = base_name
                    if multi:
                        name = f"{base_name}_TW{float(tw_len_cfg) * 1e3:g}ms"
                    data = self._three_color_curve(
                        blue, green, name=name,
                        filename=(source_filenames[0]['path'] if source_filenames else str(fn)),
                        minimum_number_of_photons=n_ph_cfg,
                        minimum_time_window_length=tw_len_cfg,
                        tttr_header_json=tttr_header_json,
                        source_filenames=source_filenames,
                    )
                    data_group.append(data)
                    logging.info(
                        "PDA3c: %s -> %d bursts", name, int(blue.shape[0])
                    )
                return data_group

            for n_ph_cfg, tw_len_cfg in configs:
                logging.debug({
                    'channels_1': channels_1,
                    'channels_2': channels_2,
                    'max_photons': self.maximum_number_of_photons,
                    'min_photons': n_ph_cfg,
                    'min_tw_len_s': tw_len_cfg,
                })
                try:
                    logging.info(
                        "PDA TRACE: calling tttrlib.Pda.compute_experimental_histograms (min_photons=%d, min_tw_len_s=%g)",
                        int(n_ph_cfg), float(tw_len_cfg),
                    )
                except Exception:
                    pass
                time_binned = str(getattr(self, "segmentation", "burst")) == "time-bins"
                if time_binned:
                    s1s2_e, ps, tttr_indices = self.time_binned_histograms(
                        t, channels_1, channels_2,
                        window_length=tw_len_cfg,
                        minimum_number_of_photons=n_ph_cfg,
                        maximum_number_of_photons=self.maximum_number_of_photons,
                    )
                else:
                    s1s2_e, ps, tttr_indices = tttrlib.Pda.compute_experimental_histograms(
                        tttr_data=t,
                        channels_1=channels_1,
                        channels_2=channels_2,
                        maximum_number_of_photons=self.maximum_number_of_photons,
                        minimum_number_of_photons=n_ph_cfg,
                        minimum_time_window_length=tw_len_cfg
                    )

                # Align experimental S1S2 orientation with the theoretical model.
                #
                # The tttrlib.Pda model S1S2 matrix (from the probability spectrum)
                # uses rows for channel 1 (green) and columns for channel 2 (red).
                # The experimental histogram produced by compute_experimental_histograms
                # is effectively stored with rows corresponding to channel 2 and
                # columns to channel 1. For consistent comparison (2D residuals and
                # 1D projections), we transpose the experimental matrix here so that
                # both share the same (green,row; red,col) convention.
                #
                # The time-binned path builds the matrix itself and already uses
                # the model orientation, so it must not be transposed again.
                try:
                    import numpy as _np
                    s1s2_e = _np.asarray(s1s2_e)
                    if s1s2_e.ndim == 2 and not time_binned:
                        s1s2_e = s1s2_e.T
                except Exception:
                    pass

                # Attach PDA-specific metadata describing the 2D S1S2 grid and
                # the 1D flattening used for fitting. We now use a standard
                # row-major flattening of the full 2D support so that the
                # resulting 1D vector can be treated in the same way as other
                # grid-based datasets (e.g. RICS).
                s1s2_shape = tuple(getattr(s1s2_e, 'shape', (0, 0)))
                ny, nx = s1s2_shape if len(s1s2_shape) == 2 else (0, 0)

                # Precompute row/column indices consistent with row-major
                # flattening so PDA-specific code (e.g. photon-number gating)
                # can still access N = row + col for each 1D bin.
                if ny > 0 and nx > 0:
                    rr, cc = np.indices((ny, nx))
                    row_indices = rr.ravel().tolist()
                    col_indices = cc.ravel().tolist()
                else:
                    row_indices, col_indices = [], []

                d = {
                    'maximum_number_of_photons': self.maximum_number_of_photons,
                    'minimum_number_of_photons': n_ph_cfg,
                    'minimum_time_window_length': tw_len_cfg,
                    # How long each observation lasted, which is what a dynamic
                    # model converts an exchange rate into transitions-per-window
                    # with. Exact under fixed-width binning; under a burst search
                    # the durations vary and this is only their lower bound, so
                    # the segmentation is recorded alongside it.
                    'segmentation': 'time-bins' if time_binned else 'burst',
                    'observation_time': float(tw_len_cfg),
                    'channels': self.channels,
                    's1s2': s1s2_e,
                    'ps': ps,
                    'row_indices': row_indices,
                    'col_indices': col_indices,
                    # Dimensionality/meta for 2D handling (kept here for PDA-
                    # specific consumers, but GUI should prefer the generic
                    # meta_data['grid'] entry added below).
                    'ndim': 2,
                    'shape': s1s2_shape,
                    # Total number of 1D points in the PDA-specific flattening
                    'size': int(len(row_indices)),
                    'tttr_indices': tttr_indices,
                }

                # Generic grid metadata describing the 2D S1S2 support and the
                # mapping from the 2D grid to the 1D histogram used for fitting.
                # This is consumed by GUI components in a model-agnostic manner
                # and uses a standard NumPy-style row-major order ('C').
                grid_meta = {
                    'ndim': 2,
                    'shape': s1s2_shape,
                    # NumPy-style order string: 'C' -> row-major, 'F' -> column-major
                    'order': 'C',
                    # Total number of 1D points in the flattened representation
                    'size': int(np.prod(s1s2_shape)) if len(s1s2_shape) == 2 else 0,
                }

                meta_all = {
                    'grid': grid_meta,
                    'tttr_header_json': tttr_header_json,
                    'tw_configs': getattr(self, 'tw_configs', None),
                    'filenames': source_filenames,
                    'reading_routine': self.reading_routine,
                    'micro_time_ranges': self.micro_time_ranges,
                }

                # Use the full S1S2 matrix as data, flattened in row-major
                # order. Elements outside the physically populated triangular
                # support (if any) will naturally carry zero counts.
                y = np.asarray(s1s2_e, dtype=float).ravel(order='C')
                x = np.arange(y.size)

                name = base_name
                if multi:
                    try:
                        tw_ms_val = float(tw_len_cfg) * 1.0e3
                        name = f"{base_name}_TW{tw_ms_val:g}ms"
                    except Exception:
                        name = base_name

                try:
                    logging.info(
                        "PDA TRACE: constructing DataCurve (name=%s, y_len=%d)",
                        name,
                        int(y.size) if hasattr(y, 'size') else -1,
                    )
                except Exception:
                    pass
                data = chisurf.core.data.DataCurve(
                    name=name,
                    filename=source_filenames[0]['path'] if source_filenames else str(fn),
                    load_filename_on_init=False,
                    data_reader=self,
                    pda=d,
                    meta_data=meta_all,
                    y=y, x=x,
                    ey=chisurf.core.fluorescence.tcspc.counting_noise(y)
                )
                data_group.append(data)
                logging.debug({'s1s2_shape': s1s2_e.shape if hasattr(s1s2_e, 'shape') else None,
                               'y_len': len(y)})
        else:
            logging.warning("PDA.read: No TTTR data could be constructed from the provided files.")

        try:
            logging.info(
                "PDA TRACE: Pda2cReader.read returning ExperimentDataGroup with %d entry(ies)",
                len(data_group),
            )
        except Exception:
            pass
        data_group.data_reader = self
        return data_group
