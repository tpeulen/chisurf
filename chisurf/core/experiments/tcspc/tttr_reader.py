from __future__ import annotations

import os.path
import pathlib
from typing import Any

import numpy as np

import chisurf.core.data
import chisurf.core.fluorescence.tcspc
from chisurf import typing

from .reader import TCSPCReader

_VIEW_JSON = pathlib.Path(__file__).parent / "tcspc_tttr.view.json"


class TCSPCTTTRReader(TCSPCReader):
    #: A measurement file: the MMFDB sample it is of is asked after it is chosen.
    asks_sample = True

    operation_type = "tcspc_histogram_computation"
    artifact_kind_source = "raw_data"
    artifact_kind_derived = "tcspc_decay"
    derived_data_format = "json"
    derived_mime_type = "application/json"

    def __init__(
        self,
        *args,
        channel_numbers=None,
        channel: int = 0,
        vh_channel_numbers=None,
        micro_time_coarsening: int = 1,
        micro_time_shift: int = 0,
        reading_routine: str | None = None,
        channel_luts: dict | None = None,
        channel_shifts: dict | None = None,
        apply_lut: bool = False,
        **kwargs,
    ):
        """Initialize a TCSPC TTTR reader.

        Parameters
        ----------
        channel_numbers : list of int, optional
            Routing channel numbers to select.
        channel : int
            Fallback single routing channel index.
        vh_channel_numbers : list of int, optional
            Routing channels of the perpendicular (VH) detectors. With them the
            routing channels are the parallel (VV) detectors and ``polarization``
            selects the output: ``vv``, ``vh``, the stacked pair ``vv/vh``, or
            ``vm`` = VV + 2 g VH. Without them every polarization reads the
            routing channels as one decay.
        micro_time_coarsening : int
            Coarsening factor for the micro-time histogram.
        micro_time_shift : int
            Histogram-level shift applied to the binned decay (in bins). This is
            distinct from the photon-level per-channel shift in *channel_shifts*.
        reading_routine : str or None
            tttrlib reading routine (e.g. ``'PTU'``).
        channel_luts : dict, optional
            Per-routing-channel TAC-linearization LUTs from the associated setup,
            ``{routing_channel: NTAC_fract}``. Applied only when *apply_lut* is set.
        channel_shifts : dict, optional
            Per-routing-channel photon-level micro-time shifts (wrapping),
            ``{routing_channel: int}``, from the associated setup.
        apply_lut : bool
            Master gate for LUT linearization during reading.
        """
        super().__init__(*args, **kwargs)
        self.channel_luts = dict(channel_luts) if channel_luts else {}
        self.channel_shifts = dict(channel_shifts) if channel_shifts else {}
        self.apply_lut = bool(apply_lut)
        if reading_routine is not None:
            self.reading_routine = reading_routine
        if not hasattr(self, "channel_numbers"):
            self.channel_numbers = None
        if channel_numbers is not None:
            try:
                self.channel_numbers = list(channel_numbers)
            except TypeError:
                self.channel_numbers = [channel_numbers]
        self.channel = int(channel)
        self.vh_channel_numbers = [int(c) for c in vh_channel_numbers] if vh_channel_numbers else []
        try:
            self.micro_time_coarsening = int(micro_time_coarsening)
        except Exception:
            self.micro_time_coarsening = 1
        try:
            self.micro_time_shift = int(micro_time_shift)
        except Exception:
            self.micro_time_shift = 0

    # -- declarative editor adapters ---------------------------------------
    @property
    def channel_numbers_str(self) -> str:
        """Comma-separated routing channels; mirrors ``channel_numbers``."""
        chs = getattr(self, "channel_numbers", None)
        if chs is None:
            chs = [getattr(self, "channel", 0)]
        try:
            return ", ".join(str(int(c)) for c in chs)
        except Exception:
            return ""

    @channel_numbers_str.setter
    def channel_numbers_str(self, value: str) -> None:
        chs = []
        for part in str(value).replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                chs.append(int(part))
            except Exception:
                continue
        if not chs:
            chs = [0]
        # A list, as the constructor stores it (an int8 array wrapped channels >= 128).
        self.channel_numbers = list(chs)
        self.channel = int(chs[0])

    @property
    def vh_channel_numbers_str(self) -> str:
        """Comma-separated VH routing channels; mirrors ``vh_channel_numbers``."""
        return ", ".join(str(int(c)) for c in (getattr(self, "vh_channel_numbers", None) or []))

    @vh_channel_numbers_str.setter
    def vh_channel_numbers_str(self, value: str) -> None:
        chs = []
        for part in str(value).replace(";", ",").split(","):
            part = part.strip()
            if part:
                try:
                    chs.append(int(part))
                except ValueError:
                    continue
        self.vh_channel_numbers = chs

    def view_spec(self):
        """Return the declarative editor spec for the TCSPC-TTTR reader."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def _get_channels(self) -> typing.Tuple[int, ...]:
        """Return the sorted tuple of routing channel numbers.

        Returns
        -------
        tuple of int
            Sorted unique channel indices.
        """
        chs = getattr(self, "channel_numbers", None)
        if chs is None:
            chs = [getattr(self, "channel", 0)]
        try:
            return tuple(sorted({int(c) for c in chs}))
        except Exception:
            return (int(getattr(self, "channel", 0) or 0),)

    def _get_micro_time_coarsening(self) -> int:
        """Return the micro-time histogram coarsening factor.

        Returns
        -------
        int
            Coarsening factor (minimum 1).
        """
        try:
            mtc = int(getattr(self, "micro_time_coarsening", 1) or 1)
        except Exception:
            mtc = 1
        if mtc <= 0:
            mtc = 1
        return mtc

    def _get_micro_time_shift(self) -> int:
        """Return the micro-time histogram shift in bins.

        Returns
        -------
        int
            Shift value (may be negative).
        """
        try:
            s = int(getattr(self, "micro_time_shift", 0) or 0)
        except Exception:
            s = 0
        return s

    def _apply_shift(self, y: np.ndarray, shift: int) -> np.ndarray:
        """Apply a circular-like shift to a histogram array.

        Positive *shift* pads at the beginning (right-shift);
        negative *shift* pads at the end (left-shift).

        Parameters
        ----------
        y : np.ndarray
            The input histogram array.
        shift : int
            Number of bins to shift.

        Returns
        -------
        np.ndarray
            The shifted array (same length as input).
        """
        arr = np.asarray(y, dtype=float)
        if arr.size == 0 or shift == 0:
            return arr
        if shift > 0:
            return np.pad(arr, (shift, 0), mode="constant")[:-shift]
        step = abs(shift)
        return np.pad(arr, (0, step), mode="constant")[step:]

    def _get_vh_channels(self) -> typing.Tuple[int, ...]:
        """Return the sorted tuple of VH routing channels (empty when unset)."""
        try:
            return tuple(sorted({int(c) for c in getattr(self, "vh_channel_numbers", None) or []}))
        except Exception:
            return ()

    def _compute_histograms(
        self, filename: str, groups: typing.Sequence[typing.Sequence[int]]
    ) -> typing.Tuple[typing.List[np.ndarray], np.ndarray]:
        """Compute one micro-time histogram per routing-channel group.

        Parameters
        ----------
        filename : str
            Path to the TTTR file.
        groups : sequence of sequence of int
            Routing-channel groups; each gives one histogram.

        Returns
        -------
        tuple
            ``(ys, x)``: one count array per group, all cut to the common
            length, and the micro-time axis in nanoseconds. The histogram shift
            is applied to every group.
        """
        routine = getattr(self, "reading_routine", None)
        if routine:
            tttr = self._open_tttr(filename, routine)
        else:
            tttr = self._open_tttr(filename)
        # Save header JSON for later metadata display (avoids re-reading the file)
        try:
            self._tttr_header_json = tttr.header.json
        except Exception:
            self._tttr_header_json = ""
        coarsening = self._get_micro_time_coarsening()
        shift = self._get_micro_time_shift()
        ys, xs = [], []
        for chs in groups:
            y_raw, x_raw = tttr.get_tttr_by_channel(list(chs)).get_microtime_histogram(coarsening)
            y = np.asarray(y_raw, dtype=float)
            if shift != 0:
                y = self._apply_shift(y, shift)
            ys.append(y)
            xs.append(np.asarray(x_raw, dtype=float))
        n = int(min([a.size for a in ys] + [a.size for a in xs])) if ys else 0
        if n <= 0:
            return [np.zeros(0, dtype=float) for _ in groups], np.zeros(0, dtype=float)
        x = max(xs, key=lambda a: a.size)[:n] * 1.0e9
        return [y[:n].astype(float) for y in ys], x.astype(float)

    def _compute_histogram(self, filename: str) -> typing.Tuple[np.ndarray, np.ndarray]:
        """Compute the micro-time histogram of the routing channels.

        Parameters
        ----------
        filename : str
            Path to the TTTR file.

        Returns
        -------
        tuple of np.ndarray
            ``(y, x)`` where *y* is the histogram counts and *x* the
            micro-time axis in nanoseconds.
        """
        (y,), x = self._compute_histograms(filename, [self._get_channels()])
        return y, x

    def read(self, filename: str | None = None, *args, **kwargs) -> chisurf.core.data.DataGroup:
        """Read a TTTR file and return a TCSPC decay curve.

        Parameters
        ----------
        filename : str, optional
            Path to the TTTR file.

        Returns
        -------
        chisurf.core.data.DataGroup
            Group containing the TCSPC decay (empty when nothing could be read).
        """
        if filename is None:
            return chisurf.core.data.DataGroup([])
        if isinstance(filename, (list, tuple)):
            if not filename:
                return chisurf.core.data.DataGroup([])
            filename = filename[0]
        if not os.path.isfile(filename):
            return chisurf.core.data.DataGroup([])
        vv_chs = self._get_channels()
        vh_chs = self._get_vh_channels()
        pol = str(getattr(self, "polarization", "vm") or "vm").lower()
        groups = [vv_chs, vh_chs] if vh_chs else [vv_chs]
        try:
            ys, t = self._compute_histograms(filename, groups)
        except Exception:
            return chisurf.core.data.DataGroup([])
        if t.size == 0:
            return chisurf.core.data.DataGroup([])
        curves: list[tuple[str | None, np.ndarray, Any, np.ndarray | None]]
        if vh_chs:
            # VV and VH measured: the VH detector's channel offset first.
            vv, vh = ys
            vh = self._apply_shift(vh, int(getattr(self, "vh_shift", 0) or 0))
            g = self._safe_float(getattr(self, "g_factor", 1.0), 1.0)
            if pol == "vv/vh":
                curves = [("VV", vv, vv_chs, None), ("VH", vh, vh_chs, None)]
            elif pol == "vv":
                curves = [("VV", vv, vv_chs, None)]
            elif pol == "vh":
                curves = [("VH", vh, vh_chs, None)]
            else:
                # Magic-angle sum; Poisson variance VV + 4 g^2 VH.
                vm = vv + 2.0 * g * vh
                ey = np.sqrt(np.maximum(vv + 4.0 * g * g * vh, 1.0))
                curves = [("VM", vm, vv_chs + vh_chs, ey)]
        else:
            curves = [(None, ys[0], vv_chs, None)]
        # Drop trailing empty bins after the last count in any curve.
        last = max(
            (int(np.nonzero(c[1] > 0)[0][-1]) + 1 for c in curves if np.any(c[1] > 0)), default=0
        )
        if last == 0:
            return chisurf.core.data.DataGroup([])
        t = t[:last]
        fn, _ = os.path.splitext(filename)
        meta_data = {}
        hdr = getattr(self, "_tttr_header_json", "")
        if hdr:
            meta_data["tttr_header_json"] = hdr
        if getattr(self, "apply_lut", False) and getattr(self, "channel_luts", None):
            meta_data["lut_linearized"] = True
        data_sets = []
        for curve in curves:
            label, y, chs = curve[0], curve[1][:last], curve[2]
            ey = (
                curve[3][:last]
                if curve[3] is not None
                else chisurf.core.fluorescence.tcspc.counting_noise(y)
            )
            ch_text = ",".join(str(int(c)) for c in chs)
            name = f"{fn}_ch({ch_text})" + (f" {label}" if label else "")
            data_set = chisurf.core.data.DataCurve(
                x=t,
                y=y,
                name=name,
                meta_data=dict(meta_data),
                experiment=self.experiment,
                data_reader=self,
                ey=ey,
            )
            data_set.filename = filename
            data_sets.append(data_set)
        data_group: chisurf.core.data.DataGroup[chisurf.core.data.DataCurve]
        if len(data_sets) > 1:
            # Stacked VV, VH: the structure the VV/VH CSV reader and the
            # simulator produce, so a fit over it takes vv/vh by position.
            data_group = chisurf.core.data.DataCurveGroup(
                data_sets, experiment=self.experiment, data_reader=self
            )
        else:
            data_group = chisurf.core.data.DataGroup(data_sets)
        if vh_chs:
            self._annotate_anisotropy_calibration(data_group)
        data_group.data_reader = self
        return data_group
