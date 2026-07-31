"""Image correlation spectroscopy (ICS) experiment reader.

Reads an image stack -- from a TIFF stack or reconstructed from TTTR/CLSM
photon data -- and correlates it into a spatiotemporal carpet
:math:`G(\\xi, \\psi, \\Delta)`. RICS, STICS, TICS and iMSD are readings of that
one carpet rather than separate analyses; see
:mod:`chisurf.core.experiments.ics.data`.
"""

from __future__ import annotations

import pathlib

import numpy as np
import tttrlib

import chisurf.core.data
from chisurf.core.experiments.core.reader import ExperimentReader
from chisurf.core.fluorescence.imaging.drift import correct_drift
from chisurf.core.roi import ROI, as_roi
from .data import FlowVector, IcsCarpet, IcsSettings, IcsTiming, lag_time
from .flow_map import FlowMap, pcf_flow_map, stics_flow_map, tile_slices
from .ics_core import compute_ics_carpet, frame_pairs, normalise_ics
from .pair_correlation import (
    PcfCarpet,
    correct_bleaching,
    kymograph,
    pcf_from_kymograph,
    pcf_from_stack,
)
from .tttr_loader import load_clsm_from_tttr

_VIEW_JSON = pathlib.Path(__file__).parent / "ics.view.json"

try:
    import imageio.v2 as imageio  # type: ignore[import]
except Exception:  # pragma: no cover - optional dependency
    try:
        import imageio  # type: ignore[import]
    except Exception:  # pragma: no cover - optional dependency
        imageio = None


def _load_tiff_stack(path: str) -> "np.ndarray":
    """Load a (possibly multi-frame, compressed) TIFF into a NumPy array.

    Image-correlation TIFF stacks are frequently LZW-compressed and multi-page.
    ``tifffile`` (used by ``imageio``) needs the optional ``imagecodecs``
    package to decode LZW and reads a single frame via ``imageio.imread``;
    Pillow decodes LZW natively and iterates every page. This helper prefers
    ``tifffile`` (full stack, all dtypes) and falls back to Pillow, so stacks
    load regardless of ``imagecodecs`` availability.

    Parameters
    ----------
    path : str
        Path to the TIFF file.

    Returns
    -------
    numpy.ndarray
        Array of shape ``(n_frames, ny, nx)`` for a stack, or ``(ny, nx)`` /
        ``(ny, nx, channels)`` for a single frame.
    """
    # 1) tifffile reads the entire stack and preserves dtype/bit-depth. It only
    #    fails for compressions (e.g. LZW) when imagecodecs is missing.
    try:
        import tifffile

        return np.asarray(tifffile.imread(path))
    except Exception:
        pass
    # 2) Pillow fallback: decodes LZW natively and iterates all pages.
    from PIL import Image, ImageSequence

    with Image.open(path) as im:
        frames = [np.asarray(frame) for frame in ImageSequence.Iterator(im)]
    if not frames:
        raise ValueError(f"No frames could be read from TIFF: {path}")
    return np.asarray(frames[0]) if len(frames) == 1 else np.asarray(frames)


class ICSReader(ExperimentReader):
    """Reader producing a spatiotemporal image-correlation carpet."""

    name: str = "Image correlation (RICS/STICS/TICS/iMSD)"
    operation_type = "image_analysis"
    artifact_kind_source = "raw_measurement"
    artifact_kind_derived = "analysis_result"

    def __init__(
            self,
            name: str = "Image correlation (RICS/STICS/TICS/iMSD)",
            reading_routine: str | None = "PTU",
            channel: int = 0,
            pixel_duration: float | None = None,
            line_duration: float | None = None,
            frame_duration: float | None = None,
            pixel_size_nm: float = 40.0,
            x_range=None,
            y_range=None,
            subtract_average: str = "frame",
            max_frame_lag: int = 0,
            fftshift: bool = True,
            roi=None,
            drift_correction: str = "",
            micro_time_ranges=None,
            *args,
            **kwargs
    ):
        """Initialize an image-correlation reader.

        Parameters
        ----------
        name : str
            Human-readable reader name.
        reading_routine : str or None
            tttrlib reading routine (e.g. ``'PTU'``).
        channel : int
            Default routing channel index.
        pixel_duration : float, optional
            Pixel dwell time in microseconds. Left unset (``None``) it is taken
            from the TTTR header of the file being read; a value given here
            wins over the header.
        line_duration : float, optional
            Line duration in milliseconds. Left unset (``None``) it is taken
            from the TTTR header of the file being read; a value given here
            wins over the header.
        frame_duration : float, optional
            Frame duration in milliseconds. When unset it is estimated as
            ``n_lines * line_duration``.
        pixel_size_nm : float
            Physical pixel size in nanometres.
        x_range : tuple of int, optional
            ROI x-range ``(start, stop)``.
        y_range : tuple of int, optional
            ROI y-range ``(start, stop)``.
        subtract_average : str
            Background subtraction mode (``'frame'``, ``'stack'``, or ``''``).
        max_frame_lag : int
            Largest frame lag :math:`\\Delta` to correlate. ``0`` yields the
            zero-lag slice only, i.e. a classic RICS map; larger values extend
            the carpet along time so STICS/TICS/iMSD become readable from it.
        fftshift : bool
            Whether to centre the zero-lag pixel in each spatial map.
        roi : ROI or dict, optional
            Region to restrict the correlation to — any
            :class:`chisurf.core.roi.ROI` or its serialised form. Pixels
            outside it are zeroed before correlating.
        drift_correction : str
            Empty to leave the stack alone, otherwise the reference mode
            (``'first'``, ``'previous'`` or ``'mean'``) used to estimate and
            remove inter-frame drift. Worth enabling whenever frame lags are
            used: a translation between frames is indistinguishable from
            diffusive decorrelation, so uncorrected drift inflates the fitted
            diffusion coefficient at exactly the long lags.
        micro_time_ranges : list, optional
            Micro-time ranges for photon selection.
        """
        super().__init__(*args, **kwargs)
        self.name = name
        self.reading_routine = reading_routine
        self.channel = int(channel)
        # Optional per-dataset imaging timing parameters. These hold what the
        # user configured — ``None`` means "auto-detect" — and are never
        # overwritten by a file: a header value is kept apart (below) and only
        # used where nothing was configured, so a corrected dwell time survives
        # every re-read. They are propagated into the ICS metadata so the models
        # can convert carpet lags into lag times.
        self.pixel_duration = pixel_duration
        self.line_duration = line_duration
        self.frame_duration = frame_duration
        # Timing seeded from the last TTTR header read, in the same units.
        self._header_pixel_duration: float | None = None
        self._header_line_duration: float | None = None
        self.pixel_size_nm = float(pixel_size_nm)
        # Optional list of TTTR routing channels defining this logical
        # tttr_channeldefinition. When present, the TTTR reader will use all of
        # these channels instead of the single "channel" index.
        if not hasattr(self, "channel_numbers"):
            self.channel_numbers = None
        self.micro_time_ranges = micro_time_ranges
        self.x_range = x_range
        self.y_range = y_range
        self.subtract_average = subtract_average
        self.max_frame_lag = int(max_frame_lag)
        self.fftshift = bool(fftshift)
        self.roi = roi
        self.drift_correction = str(drift_correction or "")

        # Optional internal cache to reuse the most recently loaded image stack
        # for previews and data loading. Keyed by filename + selection.
        self._cache_filename: str | None = None
        self._cache_images = None
        self._cache_channels = None
        self._cache_micro_time_ranges = None

    def autofitrange(self, data, **kwargs):
        """Return the full data range as the default fit interval.

        Parameters
        ----------
        data : chisurf.core.base.Data
            The experimental ICS data.

        Returns
        -------
        tuple of int
            ``(0, len(y))`` on success, ``(0, 0)`` on failure.
        """
        try:
            y = data.y
            return 0, len(y)
        except Exception:
            return 0, 0

    @property
    def pixel_duration_us(self) -> float:
        """Pixel dwell time in µs; 0.0 means auto-detect from TTTR header."""
        v = self.pixel_duration
        return float(v) if v is not None else 0.0

    @pixel_duration_us.setter
    def pixel_duration_us(self, value: float) -> None:
        self.pixel_duration = float(value) if float(value) > 0.0 else None

    @property
    def line_duration_ms(self) -> float:
        """Line scan time in ms; 0.0 means auto-detect from TTTR header."""
        v = self.line_duration
        return float(v) if v is not None else 0.0

    @line_duration_ms.setter
    def line_duration_ms(self, value: float) -> None:
        self.line_duration = float(value) if float(value) > 0.0 else None

    @property
    def frame_duration_ms(self) -> float:
        """Frame time in ms; 0.0 means estimate from the line time."""
        v = self.frame_duration
        return float(v) if v is not None else 0.0

    @frame_duration_ms.setter
    def frame_duration_ms(self, value: float) -> None:
        self.frame_duration = float(value) if float(value) > 0.0 else None

    def view_spec(self):
        """Return the declarative editor spec for ICS reader settings."""
        from chisurf.core.dataspec import load_view_spec
        return load_view_spec(_VIEW_JSON)

    def _resolve_roi(self) -> "ROI | None":
        """Return the configured region as an :class:`ROI`, or ``None``.

        Accepts either a live ROI object or its serialised dictionary, so a
        region restored from a project needs no special handling here.

        Returns
        -------
        ROI or None
            The region, or ``None`` when unset or unreadable.
        """
        try:
            return as_roi(getattr(self, "roi", None))
        except Exception:
            # A reader is restored from whatever a project file holds; an
            # unreadable region must not stop the data loading.
            return None

    def _seed_timing_from_header(self, tttr_all) -> None:
        """Read pixel/line durations from a TTTR header when possible.

        For PTU files this uses the pixel/line duration tags together with the
        global macro-time resolution. Values are stored in µs (pixel) and ms
        (line), on the ``_header_*`` attributes only: they are the fallback for
        an unset (auto-detect) setting, never a replacement for one the user
        configured. See :meth:`_effective_timing`.

        Parameters
        ----------
        tttr_all : tttrlib.TTTR
            The opened TTTR container.
        """
        try:
            hdr = getattr(tttr_all, "header", None)
        except Exception:
            hdr = None
        if hdr is None:
            return
        try:
            macro_res = float(getattr(hdr, "macro_time_resolution", 0.0) or 0.0)
        except Exception:
            return
        if macro_res <= 0.0:
            return
        try:
            pd_clk = hdr.get_pixel_duration()
        except Exception:
            pd_clk = None
        try:
            ld_clk = hdr.get_line_duration()
        except Exception:
            ld_clk = None
        if isinstance(pd_clk, (int, float)) and pd_clk > 0:
            self._header_pixel_duration = float(pd_clk) * macro_res * 1.0e6
        if isinstance(ld_clk, (int, float)) and ld_clk > 0:
            self._header_line_duration = float(ld_clk) * macro_res * 1.0e3

    def _effective_timing(self) -> tuple[float, float]:
        """Return the pixel dwell (µs) and line time (ms) a read will use.

        An explicitly configured value wins over the header of the file being
        read, which in turn wins over the scanner-agnostic defaults; that is the
        precedence the editable fields promise with their "0.0 means auto-detect
        from TTTR header" semantics.

        Returns
        -------
        tuple of float
            ``(pixel_duration_us, line_duration_ms)``.
        """
        pixel_us = self.pixel_duration_us or self._header_pixel_duration or 11.1
        line_ms = self.line_duration_ms or self._header_line_duration or 3.33
        return float(pixel_us), float(line_ms)

    def _load_images(self, fn: pathlib.Path, channels: tuple[int, ...], mtr_norm):
        """Return the image stack for a file, reading TIFF or TTTR as needed.

        Parameters
        ----------
        fn : pathlib.Path
            Path to a TIFF stack or a TTTR container.
        channels : tuple of int
            Routing channels used for TTTR/CLSM reconstruction.
        mtr_norm : tuple or None
            Normalized micro-time ranges, or ``None``.

        Returns
        -------
        numpy.ndarray or None
            Stack of shape ``(n_frames, ny, nx)``, or ``None`` when the file
            could not be interpreted as an image stack.
        """
        suffix = fn.suffix.lower()
        if suffix in (".tif", ".tiff"):
            arr = np.asarray(_load_tiff_stack(fn.as_posix()))
            if arr.ndim == 2:
                arr = arr[None, ...]
            elif arr.ndim == 3 and arr.shape[-1] in (3, 4):
                # Colour image (ny, nx, channels)
                ch = int(getattr(self, "channel", 0) or 0)
                ch = max(0, min(ch, arr.shape[-1] - 1))
                arr = arr[..., ch][None, ...]
            elif arr.ndim == 3:
                pass  # already (n_frames, ny, nx)
            elif arr.ndim == 4:
                ch = int(getattr(self, "channel", 0) or 0)
                ch = max(0, min(ch, arr.shape[-1] - 1))
                arr = arr[..., ch]
            else:
                return None
            return np.asarray(arr, dtype=float)

        # TTTR/CLSM reconstruction. The full TTTR object plus a channel list is
        # passed to CLSMImage rather than pre-filtering the TTTR, which is the
        # pattern used throughout the tttrlib examples and avoids empty
        # selections.
        if self.reading_routine:
            tttr_all = self._open_tttr(fn.as_posix(), self.reading_routine)
        else:
            tttr_all = self._open_tttr(fn.as_posix())

        self._seed_timing_from_header(tttr_all)

        mtr_arg = None
        if mtr_norm is not None:
            try:
                mtr_arg = [(int(a), int(b)) for (a, b) in mtr_norm]
            except Exception:
                mtr_arg = None

        kwargs = dict(tttr_data=tttr_all, channels=list(channels), fill=True)
        if mtr_arg:
            kwargs["micro_time_ranges"] = mtr_arg
        clsm = tttrlib.CLSMImage(**kwargs)
        images = np.asarray(clsm.intensity, dtype=float)
        if images.ndim == 2:
            images = images[None, ...]
        return images

    def read(
            self,
            filename: str = None,
            *args,
            **kwargs
    ) -> chisurf.core.data.ExperimentDataCurveGroup:
        """Read an image stack and return its spatiotemporal correlation carpet.

        Parameters
        ----------
        filename : str, optional
            Path to the TTTR file or TIFF stack.

        Returns
        -------
        chisurf.core.data.ExperimentDataCurveGroup
            Group containing one curve whose ``y`` is the flattened carpet and
            whose ``meta_data['ics']`` holds the carpet, lag grids and timing.
        """
        group = chisurf.core.data.ExperimentDataCurveGroup([])
        if filename is None:
            return group
        if isinstance(filename, (list, tuple)):
            if not filename:
                return group
            filename = filename[0]
        fn = pathlib.Path(filename)
        if not fn.is_file():
            return group

        chs = getattr(self, "channel_numbers", None)
        if chs is None:
            chs = [int(getattr(self, "channel", 0) or 0)]
        try:
            current_channels = tuple(sorted({int(c) for c in chs}))
        except Exception:
            current_channels = (int(getattr(self, "channel", 0) or 0),)

        mtr_norm = None
        mtr_value = getattr(self, "micro_time_ranges", None)
        if isinstance(mtr_value, (list, tuple)):
            tmp = []
            for r in mtr_value:
                if isinstance(r, (list, tuple)) and len(r) >= 2:
                    try:
                        tmp.append((int(r[0]), int(r[1])))
                    except Exception:
                        continue
            if tmp:
                mtr_norm = tuple(tmp)

        use_cache = (
            self._cache_filename is not None
            and str(fn) == self._cache_filename
            and self._cache_images is not None
            and getattr(self, "_cache_channels", None) == current_channels
            and getattr(self, "_cache_micro_time_ranges", None) == mtr_norm
        )
        if use_cache:
            images = np.asarray(self._cache_images, dtype=float)
        else:
            images = self._load_images(fn, current_channels, mtr_norm)
            if images is None:
                return group
            self._cache_filename = str(fn)
            self._cache_images = images
            self._cache_channels = current_channels
            self._cache_micro_time_ranges = mtr_norm

        x_range = self.x_range
        if not isinstance(x_range, (list, tuple)) or len(x_range) < 2:
            x_range = (0, -1)
        y_range = self.y_range
        if not isinstance(y_range, (list, tuple)) or len(y_range) < 2:
            y_range = (0, -1)

        # Drift correction runs before correlation: a translation between frames
        # is indistinguishable from diffusive decorrelation, so leaving it in
        # inflates the diffusion coefficient fitted from long frame lags.
        roi = self._resolve_roi()
        drift_shifts = None
        drift_mode = str(getattr(self, "drift_correction", "") or "")
        if drift_mode:
            images, drift_shifts = correct_drift(images, reference=drift_mode, roi=roi)

        max_lag = max(0, int(getattr(self, "max_frame_lag", 0) or 0))
        pixel_duration_us, line_duration_ms = self._effective_timing()
        timing = IcsTiming(
            pixel_duration_us=pixel_duration_us,
            line_duration_ms=line_duration_ms,
            frame_duration_ms=self.frame_duration_ms,
            pixel_size_nm=float(getattr(self, "pixel_size_nm", 40.0) or 40.0),
        )
        settings = IcsSettings(
            x_range=(int(x_range[0]), int(x_range[1])),
            y_range=(int(y_range[0]), int(y_range[1])),
            frame_lags=tuple(range(0, max_lag + 1)),
            subtract_average=getattr(self, "subtract_average", "frame") or "",
            timing=timing,
        )

        carpet = compute_ics_carpet(
            images, settings=settings, mask=roi, use_fftshift=bool(self.fftshift)
        )

        y = carpet.ravel()
        ey = np.asarray(carpet.error, dtype=float).ravel()
        ey = np.where(ey > 0, ey, 1.0) if ey.size == y.size else np.ones_like(y)
        x = np.arange(y.size, dtype=float)

        intensity_mean = images.mean(axis=0) if images.ndim == 3 else None

        meta_ics = carpet.to_meta()
        meta_ics.update({
            "filename": str(fn),
            "n_frames": int(images.shape[0]),
            "max_frame_lag": max_lag,
            "micro_time_ranges": mtr_norm,
            "intensity_stack": images,
            "intensity_mean": intensity_mean,
            "roi": roi.to_dict() if roi is not None else None,
            "drift_correction": drift_mode or None,
            # Keeping the shifts makes the correction auditable: a drift larger
            # than the beam waist means the long lags were compromised.
            "drift_shifts": drift_shifts,
        })

        n_lags, ny, nx = carpet.shape
        meta_all = {
            "ics": meta_ics,
            # Experiment-agnostic grid description so GUI components can reason
            # about the layout of the flattened carpet without knowing about ICS.
            "grid": {
                "ndim": 3,
                "shape": (int(n_lags), int(ny), int(nx)),
                "order": "C",
                "size": int(y.size),
            },
        }

        data = chisurf.core.data.DataCurve(
            name=fn.stem,
            x=x,
            y=y,
            ey=ey,
            filename=str(fn),
            data_reader=self,
            meta_data=meta_all,
            load_filename_on_init=False
        )
        group.append(data)
        group.data_reader = self
        return group
