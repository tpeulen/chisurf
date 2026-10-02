"""Toolkit-free scientific operations extracted from the original filter calculator.

Native component/detector records replace widget reads. Numerical operations,
IRF alignment, nuisance models, fit ranges, and lifetime/FRET fitting are shared
unchanged with the original algorithms.
"""

from __future__ import annotations

import logging
import pathlib

import numpy as np

from chisurf.core.fluorescence.decay import (
    afterpulse_decay_pattern,
    optimize_synthetic_scatter_pattern,
    sample_decay_shot_noise,
    scattered_light_decay_pattern,
)

from ..api import FilterResult, compute_filters, synthetic_component_decay
from .decay_io import load_vector


class ScientificOperations:
    def _fit_period_ns(self, n_bins: int, dt: float) -> float | None:
        """Laser period (ns) for periodic convolution, or None when disabled.

        Uses the Instrument dock's period; 0 ⇒ the full micro-time window.
        """
        instr = self._instrument()
        if not instr.get("periodic"):
            return None
        period = float(instr.get("period_ns", 0.0) or 0.0)
        return period if period > 0.0 else float(n_bins) * float(dt)

    def _pattern_bin_width_ns(self) -> float:
        if getattr(self, "_data_dt_ns", 0.0) > 0.0:
            return float(self._data_dt_ns)
        for index in range(len(self.components)):
            source = self.components.__getitem__(index).source
            if isinstance(source, dict) and source.get("bin_width"):
                return float(source["bin_width"])
        return 0.05

    def _micro_time_axis(self, header, microtimes: np.ndarray, n_tac: int):
        """Apply the optional micro-time binning and capture the TAC bin width.

        Reads the micro-time resolution from the TTTR ``header`` (seconds → ns),
        multiplies it by the coarsening factor, and stores it in ``_data_dt_ns``
        so the lifetime filters use the same micro-time axis as the data / the
        correlator. Returns ``(microtimes, n_tac)`` after coarsening.
        """
        try:
            resolution_s = float(getattr(header, "micro_time_resolution", 0.0) or 0.0)
        except Exception:
            resolution_s = 0.0
        b = max(1, int(getattr(self, "_micro_time_binning", 1)))
        if b > 1:
            microtimes = microtimes // b
            n_tac = (int(n_tac) + b - 1) // b
        if resolution_s > 0.0:
            self._data_dt_ns = resolution_s * 1000000000.0 * b
        return (microtimes, int(n_tac))

    def _nuisance_patterns(
        self,
        total_decay: np.ndarray,
        component_decays: list[np.ndarray] | None = None,
        detector_name: str | None = None,
        role: str = "",
    ) -> tuple[list[np.ndarray], list[str]]:
        total = np.asarray(total_decay, dtype=float).ravel()
        n_bins = total.size
        patterns: list[np.ndarray] = []
        labels: list[str] = []
        if self.options_model.fit_background:
            patterns.append(afterpulse_decay_pattern(n_bins))
            labels.append("Afterpulse / constant")
        if self.options_model.scatter_irf:
            detector = detector_name or (self.detectors.selected[:1] or ["default"])[0]
            configured_path = self.detectors.irf_path(detector, role)
            if configured_path:
                irf_path = pathlib.Path(configured_path)
                if not irf_path.is_file():
                    raise ValueError(f"Scatter IRF for {detector} does not exist: {irf_path}")
                shift = float(self.detectors.shift(detector, role) or 0.0)
                measured = self._shift_irf(
                    load_vector(irf_path), shift, self._pattern_bin_width_ns()
                )
                scatter = scattered_light_decay_pattern(measured, n_bins)
                source = "measured"
            else:
                det_irf = self._detector_irf(detector, role, n_bins=n_bins)
                if det_irf is not None and np.any(np.asarray(det_irf) > 0.0):
                    scatter = scattered_light_decay_pattern(det_irf, n_bins)
                    source = "detector-IRF"
                else:
                    basis = [np.asarray(d, dtype=float).ravel() for d in component_decays or []]
                    basis = [
                        d
                        for d in basis
                        if d.size == total.size
                        and np.all(np.isfinite(d))
                        and np.all(d >= 0.0)
                        and (d.sum() > 0.0)
                    ]
                    scatter, fit = optimize_synthetic_scatter_pattern(
                        total,
                        basis,
                        bin_width_ns=self._pattern_bin_width_ns(),
                        initial_fwhm_ns=self.detectors.width(detector, role),
                        shape=self.detectors.skew(detector, role),
                        include_constant=self.options_model.fit_background,
                    )
                    key = f"{detector}:{role}" if role else detector
                    self._synthetic_scatter_fits[key] = fit
                    source = "fitted"
            patterns.append(scatter)
            labels.append(f"Scatter / IRF ({detector}, {source})")
            self._irf_by_detector[str(detector)] = np.asarray(scatter, dtype=float)
        return (patterns, labels)

    def _has_total_decay(self) -> bool:
        return bool(self._total_paths) or self._total_vector is not None

    def _total_decay(self, chs: list[str] | None = None) -> np.ndarray:
        if self._total_paths:
            return self._load_and_sum_vectors(self._total_paths, chs)
        if self._total_vectors_by_detector and chs:
            selected = [
                self._total_vectors_by_detector[name]
                for name in chs
                if name in self._total_vectors_by_detector
            ]
            if selected:
                return np.sum(selected, axis=0)
        if self._total_vector is not None:
            return np.asarray(self._total_vector, dtype=float).copy()
        raise ValueError("No mixed total decay is available.")

    def _shift_irf(self, irf, shift_ns: float, dt: float):
        """Shift an IRF vector by ``shift_ns`` (sub-bin, linear interp, zero edges).

        A positive shift moves the IRF to later times. Applied uniformly to both
        measured and synthetic IRFs so a detector's timing offset is corrected the
        same way regardless of how the IRF was obtained.
        """
        if irf is None or not shift_ns or dt <= 0.0:
            return irf
        v = np.asarray(irf, dtype=float).ravel()
        idx = np.arange(v.size, dtype=float) - float(shift_ns) / float(dt)
        return np.interp(idx, np.arange(v.size, dtype=float), v, left=0.0, right=0.0)

    def _current_n_bins(self) -> int:
        """Bin count of the active total decay (data-derived, not a fixed 256).

        For file-/correlator-backed totals ``_total_vector`` is ``None``, so the
        length must come from the loaded decay — otherwise a synthetic IRF built at
        the default 256 bins is far shorter than the real micro-time axis and a
        fitted shift can push its prompt off the end.
        """
        if self._total_vector is not None:
            return int(self._total_vector.size)
        try:
            chs = self.detectors.selected or None if self.detectors.names else None
            return int(np.asarray(self._total_decay(chs)).size)
        except Exception:
            return 256

    def _detector_irf(self, detector_name: str, role: str = "", n_bins: int | None = None):
        """Return a detector's IRF (measured file or synthetic Gaussian) for FRET decays.

        The per-detector time shift from the Detectors table is applied to the
        returned IRF (measured or synthetic) so the modelled prompt lines up with
        the measurement. ``n_bins`` defaults to the active total's length.
        """
        import numpy as np

        from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

        n = int(n_bins) if n_bins else self._current_n_bins()
        dt = float(self._pattern_bin_width_ns())
        shift = float(self.detectors.shift(detector_name, role) or 0.0)
        configured = self.detectors.irf_path(detector_name, role)
        if configured and pathlib.Path(configured).is_file():
            return self._shift_irf(load_vector(pathlib.Path(configured)), shift, dt)
        fwhm = float(self.detectors.width(detector_name, role) or 0.0)
        if fwhm <= 0.0:
            return None
        time = np.arange(n, dtype=float) * dt
        irf = synthetic_irf(
            time, 2.0 * fwhm, fwhm, shape=float(self.detectors.skew(detector_name, role) or 0.0)
        )
        shifted = self._shift_irf(irf, shift, dt)
        if shifted is None or not np.any(np.asarray(shifted) > 0.0):
            return irf if np.any(irf > 0.0) else None
        return shifted

    def _calibration_seed(self) -> dict:
        """Crosstalk factors offered to the FRET-species editor.

        The Instrument dock is the more specific statement: it starts as the
        selected setup's stored calibration and then carries whatever the user
        edited. Falling back to the setup keeps the seed working before that
        dock has been built.
        """
        from chisurf.core.fluorescence.fret.calibration import setup_calibration_values

        cal = setup_calibration_values(self._detector_settings)
        if hasattr(self, "instrument_model"):
            cal.update(self._instrument())
        seed = {}
        for key in ("alpha", "beta", "gamma", "delta", "forster_radius"):
            value = cal.get(key)
            if value is not None:
                seed[key] = float(value)
        return seed

    @staticmethod
    def _resize_pattern(pattern: np.ndarray, n_bins: int) -> np.ndarray:
        pattern = np.asarray(pattern, dtype=float).ravel()
        if pattern.size >= n_bins:
            return pattern[:n_bins]
        resized = np.zeros(n_bins, dtype=float)
        resized[: pattern.size] = pattern
        return resized

    @staticmethod
    def _apply_pattern_shot_noise(pattern: np.ndarray, source: dict) -> np.ndarray:
        pattern = np.asarray(pattern, dtype=float).ravel()
        if not source.get("shot_noise", False):
            return pattern
        sampled = sample_decay_shot_noise(
            pattern,
            photon_count=float(source.get("photon_count", 100000)),
            seed=int(source.get("noise_seed", 0)),
        )
        total = sampled.sum()
        if total <= 0.0:
            raise ValueError("shot-noise sampling produced an empty decay")
        return sampled / total

    def _species_item_pattern(self, item, n_bins: int, chs: list[str] | None):
        """Resolve a file-backed or synthetic list item to one decay pattern."""
        source = item.source
        if isinstance(source, dict) and source.get("type") == "synthetic":
            detector_patterns = source.get("patterns_by_detector") or {}
            if detector_patterns:
                selected = [
                    np.asarray(detector_patterns[channel], dtype=float)
                    for channel in chs or []
                    if channel in detector_patterns
                ]
                if selected:
                    pattern = np.sum(
                        [self._resize_pattern(value, n_bins) for value in selected], axis=0
                    )
                else:
                    pattern = np.asarray(
                        detector_patterns.get(
                            "__default__", next(iter(detector_patterns.values()))
                        ),
                        dtype=float,
                    )
                return (self._resize_pattern(pattern, n_bins), dict(source))
            irf = None
            if source.get("irf_path"):
                irf = load_vector(pathlib.Path(source["irf_path"]))
            source = dict(source)
            source["start_bin"] = min(int(source.get("start_bin", 0)), n_bins - 1)
            pattern = synthetic_component_decay(n_bins, source, irf=irf)
            return (pattern, dict(source))
        paths = [pathlib.Path(path) for path in source]
        pattern = self._load_and_sum_vectors(paths, chs)
        return (self._resize_pattern(pattern, n_bins), [str(path.absolute()) for path in paths])

    def _mask_to_fit_range(self, values, detector: str | None = None) -> np.ndarray:
        """Blank residuals outside the fit range (NaN → not drawn).

        Residuals are only meaningful inside the fit window, so bins outside
        ``[start, stop]`` are set to NaN; chiplot breaks a line at non-finite
        samples, so the excluded region is simply not drawn. When a ``detector``
        is given its per-detector range override (if any) is used.
        """
        v = np.asarray(values, dtype=float).copy()
        start, stop = self._detector_fit_range(detector, v.size)
        if start > 0 or stop < v.size:
            v[:start] = np.nan
            v[stop:] = np.nan
        return v

    def _detector_fit_range(self, detector: str | None, n_bins: int) -> tuple[int, int]:
        """Per-detector fit range (override or the global region), clamped to n_bins."""
        rng = self._detector_fit_ranges.get(detector) if detector else None
        start, stop = rng if rng is not None else self._fit_range(n_bins)
        start = max(0, min(int(start), int(n_bins) - 1))
        stop = max(start + 1, min(int(stop), int(n_bins)))
        return (start, stop)

    def _zero_filters_outside(self, filters, start: int, stop: int) -> np.ndarray:
        """Zero every filter column outside ``[start, stop]``.

        Photons outside the fit range carry no fitted model, so their filter
        weights are set to zero — the filters are only defined where the decay was
        fitted (requested behaviour: "filters outside the fitting range are zeroed").
        """
        f = np.array(filters, dtype=float, copy=True)
        if f.ndim == 2:
            f[:, : max(0, int(start))] = 0.0
            f[:, int(stop) :] = 0.0
        return f

    def _apply_range_to_result(self, result, detector: str | None) -> None:
        """Zero a result's filters outside that detector's fit range, in place.

        Handles both single/multi/stacked :class:`FilterResult` (``.filters``) and
        the anisotropy :class:`FilterResultMFD` (``.filters_par``/``.filters_perp``).
        The *un-zeroed* filters are cached on the result the first time, so a later
        range change can re-zero (even widen) without a refit.
        """
        if result is None:
            return
        for attr in ("filters", "filters_par", "filters_perp"):
            f = getattr(result, attr, None)
            if f is None:
                continue
            cache_attr = f"_{attr}_full"
            base = getattr(result, cache_attr, None)
            if base is None:
                base = np.array(f, dtype=float, copy=True)
                try:
                    setattr(result, cache_attr, base)
                except Exception:
                    pass
            n_bins = int(np.asarray(base).shape[1])
            start, stop = self._detector_fit_range(detector, n_bins)
            setattr(result, attr, self._zero_filters_outside(base, start, stop))

    def _single_detector(self) -> str | None:
        """The detector to attribute a single-channel result to (or None → global)."""
        chs = self.detectors.selected if self.detectors.names else None
        return chs[0] if chs and len(chs) == 1 else None

    def _ranged_filters(
        self,
        total_data,
        species_data,
        *,
        detector,
        total_path,
        species_patterns,
        nuisance_decays,
        nuisance_labels,
    ):
        """Compute fFCS filters **over the detector's fit range** and embed back.

        The filters/g-matrix are solved on the ``[start, stop]`` slice only, so the
        reconstruction and residuals are not biased by the excluded pre-prompt and
        far-tail bins (the cause of a systematic tail offset). The full-length
        result has the in-range columns filled and zeros/original outside.
        """
        total = np.asarray(total_data, dtype=float).ravel()
        n_bins = int(total.size)
        start, stop = self._detector_fit_range(detector, n_bins)
        species = [self._resize_pattern(np.asarray(s, dtype=float), n_bins) for s in species_data]
        nuis = [
            self._resize_pattern(np.asarray(d, dtype=float), n_bins) for d in nuisance_decays or []
        ]
        ranged = compute_filters(
            total[start:stop],
            [s[start:stop] for s in species],
            total_path=total_path,
            species_patterns=species_patterns,
            nuisance_decays=[d[start:stop] for d in nuis] or None,
            nuisance_labels=nuisance_labels,
            reject_nuisance=True,
        )
        n_filt = int(np.asarray(ranged.filters).shape[0])
        filters = np.zeros((n_filt, n_bins), dtype=float)
        filters[:, start:stop] = np.asarray(ranged.filters)
        recon = total.copy()
        recon[start:stop] = np.asarray(ranged.reconstruction)
        wres = np.zeros(n_bins, dtype=float)
        wres[start:stop] = np.asarray(ranged.weighted_residuals)
        return FilterResult(
            filters=filters,
            reconstruction=recon,
            weighted_residuals=wres,
            total_decay=total,
            species_decays=species,
            metadata=ranged.metadata,
            total_path=total_path,
            species_patterns=species_patterns,
            nuisance_count=int(ranged.nuisance_count),
            nuisance_labels=list(ranged.nuisance_labels or []),
        )

    def _measured_irf_vector(self, detector: str | None, role: str = ""):
        """Return a detector's *measured* IRF vector, or ``None`` if none is loaded."""
        if not detector:
            return None
        configured = self.detectors.irf_path(detector, role)
        if configured and pathlib.Path(configured).is_file():
            return np.asarray(load_vector(pathlib.Path(configured)), dtype=float).ravel()
        return None

    def _auto_fit_components(self, n_components: int | None = None) -> None:
        """Auto-fit the mixed decay to N lifetime components and add them as species.

        The draggable fit region on the reconstruction plot sets the fit window.
        When the primary detector carries a **measured IRF** it is used directly and
        a tail fit (range start past the prompt) resolves the lifetimes. When **no
        IRF is loaded** the synthetic Gaussian IRF is *fitted jointly* — its width is
        a free parameter — so the fit window is extended down to the prompt
        (``fit_lo = 0``) to make the IRF identifiable, and the fitted FWHM is written
        back to every selected detector that lacks a measured IRF. Each resolved
        lifetime is appended as one synthetic species, its per-detector pattern
        convolved with that detector's IRF.
        """
        from chisurf.core.fluorescence.decay_fit_model import fit_lifetime_model
        from chisurf.core.fluorescence.tcspc.irf import FWHM_TO_SIGMA

        if not self._has_total_decay():
            raise ValueError("Load a mixed total decay first.")
            return
        settings = dict(self._auto_fit_settings)
        kind = settings["kind"]
        if n_components is None:
            n_components = int(settings["n_components"])
        chs = self.detectors.selected if self.detectors.names else None
        total = np.asarray(self._total_decay(chs[:1] if chs else None), dtype=float).ravel()
        dt = self._pattern_bin_width_ns()
        n_bins = int(total.size)
        self._init_fit_region(total)
        start, stop = self._fit_range(n_bins)
        primary = chs[0] if chs else None
        measured = self._measured_irf_vector(primary)
        fit_irf = measured is None
        fit_lo = int(start)
        include_background = bool(self.options_model.fit_background)
        include_scatter = bool(self.options_model.scatter_irf)
        period = self._fit_period_ns(n_bins, dt)
        fwhm0 = max(dt, float(self.detectors.width(primary, "") or 0.2)) if primary else 0.2
        skew0 = float(self.detectors.skew(primary, "") or 0.0) if primary else 0.0
        shared = dict(
            bin_width=dt,
            irf=measured,
            start_bin=fit_lo,
            stop_bin=stop,
            fit_irf=fit_irf,
            irf_width=fwhm0 * FWHM_TO_SIGMA,
            irf_skew=skew0,
            fit_background=include_background,
            fit_scatter=include_scatter,
            period=period,
        )
        try:
            if kind == "fret":
                from chisurf.core.fluorescence.decay_fit_model import fit_fret_model

                instrument = self._instrument()
                result = fit_fret_model(
                    total,
                    n_states=int(n_components),
                    donor_lifetime=float(settings["tau_max"]),
                    forster_radius=float(instrument.get("forster_radius") or 52.0),
                    **shared,
                )
                taus = np.asarray([], dtype=float)
            else:
                result = fit_lifetime_model(
                    total,
                    n_components=int(n_components),
                    tau_bounds=(float(settings["tau_min"]), float(settings["tau_max"])),
                    **shared,
                )
                taus = result["lifetimes"]
        except Exception as error:
            raise ValueError(str(error))
            return
        if kind == "fret":
            amps = np.asarray(result["fractions"], dtype=float)
        else:
            amps = np.asarray(result["amplitudes"], dtype=float) * taus
        scale = float(amps.sum()) or 1.0
        self._auto_fit_result = result
        pass
        detector_names = list(chs or [])
        fitted_fwhm = float(result.get("irf_width") or 0.0) / FWHM_TO_SIGMA
        fitted_skew = result.get("irf_skew")
        if fit_irf and fitted_fwhm > 0:
            peak_ns = result.get("irf_peak")
            if peak_ns is None:
                peak_ns = 2.0 * fitted_fwhm
            shift = peak_ns - 2.0 * fitted_fwhm
            for det in detector_names or ([primary] if primary else []):
                if self._measured_irf_vector(det) is None:
                    self.detectors.set_width(det, float(fitted_fwhm), "")
                    if fitted_skew is not None:
                        self.detectors.set_skew(det, float(fitted_skew), "")
                    self.detectors.set_shift(det, float(shift), "")
        comp_start = 0
        self._suspend_compute = True
        try:
            self.components.clear()
            if kind == "fret":
                self._add_fret_autofit_species(
                    amps,
                    taus,
                    scale,
                    dt,
                    comp_start,
                    n_bins,
                    detector_names,
                    period=period,
                    efficiencies=result["efficiencies"],
                    tau_d0=result["donor_lifetime"],
                    donor_only_fraction=result["donor_only_fraction"],
                )
            else:
                self._add_autofit_species(
                    kind,
                    amps,
                    taus,
                    scale,
                    dt,
                    comp_start,
                    n_bins,
                    detector_names,
                    apply_irf=True,
                    period=period,
                )
        finally:
            self._suspend_compute = False
        self._on_data_changed()
        if kind == "fret":
            parts = ", ".join(
                (
                    f"{float(a) / scale:.0%}·E={float(e):.2f}"
                    for a, e in zip(amps, result["efficiencies"])
                )
            )
            n_species = len(result["efficiencies"])
        else:
            parts = ", ".join(
                (f"{float(a) / scale:.0%}·{float(t):.2f}ns" for a, t in zip(amps, taus))
            )
            n_species = len(taus)
        label = "FRET states" if kind == "fret" else "components"
        if fit_irf and fitted_fwhm > 0:
            irf_note = f", IRF FWHM {fitted_fwhm:.3f} ns / shift {shift:+.3f} ns / skew {float(fitted_skew or 0.0):+.2f}"
        else:
            irf_note = ""
        nuis = []
        if include_scatter and result.get("scatter"):
            nuis.append(f"scatter {result['scatter']:.3g}")
        if include_background and result.get("background"):
            nuis.append(f"bkg {result['background']:.3g}")
        nuis_note = " [" + ", ".join(nuis) + "]" if nuis else ""
        msg = f"Auto-fit [{fit_lo}–{stop}]: {n_species} {label} (χ²ᵣ={result['chi2_reduced']:.3g}{irf_note}) — {parts}{nuis_note}."
        self._update_status(msg)
        if hasattr(self, "lbl_autofit_status"):
            pass
        logging.info(msg)

    def _add_autofit_species(
        self,
        kind,
        amps,
        taus,
        scale,
        dt,
        start,
        n_bins,
        detector_names,
        apply_irf: bool = False,
        period=None,
    ):
        from chisurf.core.fluorescence.decay import synthetic_decay

        if kind == "fret":
            self._add_fret_autofit_species(
                amps, taus, scale, dt, start, n_bins, detector_names, period=period
            )
        else:
            for amp, tau in zip(amps, taus):
                frac = float(amp) / scale
                source = {
                    "type": "synthetic",
                    "model": "lifetime_spectrum",
                    "name": f"τ={float(tau):.2f} ns ({frac:.0%})",
                    "amplitudes": [frac],
                    "lifetimes": [float(tau)],
                    "bin_width": float(dt),
                    "start_bin": int(start),
                    "irf_path": None,
                    "period_ns": float(period) if period else 0.0,
                }
                patterns = {}
                for name in detector_names:
                    irf = self._detector_irf(name, n_bins=int(n_bins)) if apply_irf else None
                    if irf is not None and (not np.any(np.asarray(irf) > 0.0)):
                        irf = None
                    patterns[name] = synthetic_decay(
                        n_bins,
                        [float(tau)],
                        bin_width=float(dt),
                        irf=irf,
                        start_bin=int(start),
                        normalize=True,
                        period=period,
                    ).tolist()
                if patterns:
                    patterns["__default__"] = patterns[detector_names[0]]
                    source["patterns_by_detector"] = patterns
                self.add_component(source)

    def _add_fret_autofit_species(
        self,
        amps,
        taus,
        scale,
        dt,
        start,
        n_bins,
        detector_names,
        period=None,
        efficiencies=None,
        tau_d0=None,
        donor_only_fraction=0.0,
    ):
        """Add FRET species from fitted efficiencies, or derive them from lifetimes.

        With ``efficiencies`` (from a real ``FRETModel`` fit) each value is used
        directly, together with the fitted ``tau_d0`` and, when non-zero, an extra
        donor-only species carrying ``donor_only_fraction``.

        Without them the efficiencies are *derived*: the longest fitted lifetime is
        taken as the unquenched donor τ_D0 and each τᵢ becomes Eᵢ = 1 − τᵢ/τ_D0.
        That is the weaker inference — it assumes the slowest component is
        unquenched donor — and is kept for callers that only have lifetimes.

        Each species is expanded to per-detector coupled decays and added — a
        starting FRET set the user refines in the editor.
        """
        from chisurf.core.fluorescence.fret.species_decay import fret_species_detector_patterns

        if efficiencies is not None:
            tau_d0 = float(tau_d0 or 1.0)
            pairs = [(float(a), float(e)) for a, e in zip(amps, efficiencies)]
            if float(donor_only_fraction) > 0.001:
                pairs.append((float(donor_only_fraction) * scale, 0.0))
        else:
            tau_d0 = float(max(taus)) if len(taus) else 1.0
            pairs = [
                (float(a), float(np.clip(1.0 - float(t) / tau_d0, 0.0, 0.999)))
                for a, t in zip(amps, taus)
            ]
        dets = detector_names or ["green", "red", "yellow"]
        for amp, efficiency in pairs:
            frac = float(amp) / scale
            tau_d0 * (1.0 - efficiency)
            state = "d_only" if efficiency < 0.001 else "da"
            source = {
                "type": "synthetic",
                "model": "fret_species",
                "name": f"donor-only τ={tau_d0:.2f} ({frac:.0%})"
                if state == "d_only"
                else f"DA E={efficiency:.2f} ({frac:.0%})",
                "state": state,
                "donor_spectrum": [1.0, tau_d0],
                "acceptor_spectrum": [1.0, 2.0],
                "fret_mode": "efficiency",
                "transfer_efficiency": efficiency,
                "bin_width": float(dt),
                "period_ns": float(period) if period else 0.0,
                "crosstalk": {
                    k: self._instrument().get(k) for k in ("alpha", "beta", "gamma", "delta")
                },
                "forster_radius": self._instrument().get("forster_radius"),
            }
            try:
                patterns = fret_species_detector_patterns(
                    source, dets, n_bins, irf_for_detector=self._detector_irf
                )
                source["patterns_by_detector"] = {
                    k: np.asarray(v, dtype=float).tolist() for k, v in patterns.items()
                }
            except Exception as error:
                logging.warning(f"FRET auto-fit species build failed: {error}")
            self.add_component(source)

    def _get_cache_key(self, paths: list[pathlib.Path], chs: list[str] | None) -> tuple:
        """Generate cache key from file paths and detector channels."""
        path_tuple = tuple(str(p.absolute()) for p in paths)
        ch_tuple = tuple(sorted(chs)) if chs else ()
        return (path_tuple, ch_tuple)

    def _load_routing_channels(self, path: pathlib.Path) -> dict[int, np.ndarray]:
        """Load and cache all routing channel histograms for a TTTR file.

        Returns dict mapping routing_channel_number -> histogram.
        """
        path_str = str(path.absolute())
        if path_str in self._routing_cache:
            return self._routing_cache[path_str]
        ext = path.suffix.lower()
        routing_histograms = {}
        if ext in (".spc", ".ptu", ".ht3", ".tttr"):
            import tttrlib

            try:
                if ext == ".spc":
                    try:
                        data = tttrlib.TTTR(str(path), "SPC-130")
                    except Exception:
                        data = tttrlib.TTTR(str(path))
                else:
                    data = tttrlib.TTTR(str(path))
                header = data.get_header()
                try:
                    n_tac = header.number_of_micro_time_channels
                except AttributeError:
                    try:
                        n_tac = header["number_of_micro_time_channels"]
                    except (KeyError, TypeError):
                        n_tac = 4096
                microtimes = data.micro_times
                routing = data.routing_channels
                microtimes, n_tac = self._micro_time_axis(header, microtimes, n_tac)
                unique_routing = np.unique(routing)
                for rch in unique_routing:
                    mask = (routing == rch) & (microtimes >= 0) & (microtimes < n_tac)
                    hist = np.zeros(n_tac, dtype=np.float64)
                    np.add.at(hist, microtimes[mask], 1)
                    routing_histograms[int(rch)] = hist
            except Exception as e:
                logging.warning(f"Error loading routing channels from {path.name}: {e}")
        elif ext == ".bst":
            from .decay_io import parse_bst_file

            tttr_path, ranges = parse_bst_file(path)
            if tttr_path and ranges:
                import tttrlib

                try:
                    data = tttrlib.TTTR(str(tttr_path))
                    header = data.get_header()
                    try:
                        n_tac = header.number_of_micro_time_channels
                    except AttributeError:
                        try:
                            n_tac = header["number_of_micro_time_channels"]
                        except (KeyError, TypeError):
                            n_tac = 4096
                    microtimes = data.micro_times
                    routing = data.routing_channels
                    microtimes, n_tac = self._micro_time_axis(header, microtimes, n_tac)
                    unique_routing = np.unique(routing)
                    for rch in unique_routing:
                        hist = np.zeros(n_tac, dtype=np.float64)
                        for start, end in ranges:
                            if start < len(microtimes) and end <= len(microtimes):
                                burst_mt = microtimes[start : min(end + 1, len(microtimes))]
                                burst_rt = routing[start : min(end + 1, len(routing))]
                                mask = (burst_rt == rch) & (burst_mt >= 0) & (burst_mt < n_tac)
                                np.add.at(hist, burst_mt[mask], 1)
                        routing_histograms[int(rch)] = hist
                except Exception as e:
                    logging.warning(f"Error loading BST routing channels from {path.name}: {e}")
        self._routing_cache[path_str] = routing_histograms
        return routing_histograms

    def _load_and_sum_vectors(self, paths: list[pathlib.Path], chs: list[str] | None) -> np.ndarray:
        """Load and sum vectors with routing channel caching."""
        cache_key = self._get_cache_key(paths, chs)
        if cache_key in self._decay_cache:
            return self._decay_cache[cache_key].copy()
        routing_channels = set()
        if chs:
            for ch_name in chs:
                if ch_name.startswith("routing_"):
                    try:
                        routing_channels.add(int(ch_name.split("_")[1]))
                    except Exception:
                        pass
                elif self._detector_settings:
                    det_config = self._detector_settings.get("detectors", {}).get(ch_name, {})
                    det_chs = det_config.get("chs", [])
                    routing_channels.update(det_chs)
        max_size = 0
        all_histograms = []
        for path in paths:
            ext = path.suffix.lower()
            if ext in (".spc", ".ptu", ".ht3", ".tttr", ".bst"):
                routing_hists = self._load_routing_channels(path)
                if routing_channels:
                    combined = None
                    for rch in routing_channels:
                        if rch in routing_hists:
                            if combined is None:
                                combined = routing_hists[rch].copy()
                            else:
                                combined += routing_hists[rch]
                    if combined is not None:
                        all_histograms.append(combined)
                        max_size = max(max_size, combined.size)
                else:
                    combined = None
                    for hist in routing_hists.values():
                        if combined is None:
                            combined = hist.copy()
                        else:
                            combined += hist
                    if combined is not None:
                        all_histograms.append(combined)
                        max_size = max(max_size, combined.size)
            else:
                vec = load_vector(path, chs=chs, detector_settings=self._detector_settings)
                all_histograms.append(vec)
                max_size = max(max_size, vec.size)
        if max_size == 0 or not all_histograms:
            logging.warning(f"No valid histogram data loaded for paths: {[p.name for p in paths]}")
            return np.zeros(4096, dtype=np.float64)
        summed = np.zeros(max_size, dtype=np.float64)
        for hist in all_histograms:
            if hist.size < max_size:
                padded = np.zeros(max_size, dtype=np.float64)
                padded[: hist.size] = hist
                summed += padded
            else:
                summed += hist
        self._decay_cache[cache_key] = summed.copy()
        return summed
