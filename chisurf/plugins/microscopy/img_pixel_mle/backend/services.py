"""RPC service registration for img_pixel_mle."""

from __future__ import annotations

import logging
from typing import Any

from ..api.contract import (
    METHOD_ANALYZE,
    METHOD_CONTRACT,
    contract_descriptor,
    service_error,
    service_success,
)

logger = logging.getLogger(__name__)


def register_services(dispatcher: Any) -> None:
    """Register all img_pixel_mle RPC handlers with *dispatcher*."""
    dispatcher.register(METHOD_ANALYZE, _handle_analyze)
    dispatcher.register(METHOD_CONTRACT, _handle_contract)


def _build_irf_vv_vh(irf_file: str, settings: Any) -> Any:
    """Build a prepared VV/VH-format IRF histogram from an IRF TTTR file."""
    import numpy as np
    import tttrlib

    from ..api.pixel_mle import prepare_irf

    irf_tttr = tttrlib.TTTR(irf_file)
    binning = max(1, int(settings.micro_time_binning))
    n_ch = irf_tttr.header.number_of_micro_time_channels // binning
    start, stop = int(settings.micro_time_start), int(settings.micro_time_stop)
    micro = irf_tttr.micro_times // binning
    rc = irf_tttr.routing_channels

    def _hist(channels):
        sel = np.isin(rc, list(channels))
        return np.bincount(micro[sel], minlength=n_ch)[start:stop].astype(np.float64)

    irf_p, irf_s = prepare_irf(
        _hist(settings.detector_chs_p),
        _hist(settings.detector_chs_s),
        threshold=settings.irf_threshold,
        shift=settings.irf_shift,
        shift_sp=settings.shift_sp,
        shift_ss=settings.shift_ss,
        threshold_vv=settings.irf_threshold_vv,
        threshold_vh=settings.irf_threshold_vh,
    )
    return np.concatenate([irf_p, irf_s])


def _handle_analyze(params: dict[str, Any]) -> dict[str, Any]:
    """Run pixel-wise MLE analysis headlessly through the Qt-free core."""
    try:
        import os

        import numpy as np
        import tttrlib

        from ..api.models import PixelMleRequest
        from ..api.models import PixelMleSettings as ApiSettings
        from ..core import PixelMleSettings, fit_pixel_lifetimes

        settings_raw = params.get("settings") or {}
        known = {f.name for f in ApiSettings.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        settings = ApiSettings(**{k: v for k, v in settings_raw.items() if k in known})
        request = PixelMleRequest(
            files=params["files"],
            irf_file=params["irf_file"],
            output_dir=params.get("output_dir", ""),
            settings=settings,
        )
        logger.info("img_pixel_mle.analyze.run: %d file(s)", len(request.files))

        irf = _build_irf_vv_vh(request.irf_file, settings)
        window = int(settings.micro_time_stop) - int(settings.micro_time_start)
        background = None
        if settings.use_bg and window > 0:
            background = np.concatenate(
                [
                    np.full(window, settings.bg_p / window, dtype=np.float64),
                    np.full(window, settings.bg_s / window, dtype=np.float64),
                ]
            )

        processed: list[str] = []
        output_paths: list[str] = []
        period_ns: float | None = None
        for f in request.files:
            tttr = tttrlib.TTTR(f)
            if period_ns is None:
                header = tttr.header
                period_ns = (
                    header.number_of_micro_time_channels * header.micro_time_resolution * 1e9
                )
            core_settings = PixelMleSettings(
                channels_parallel=settings.detector_chs_p,
                channels_perpendicular=settings.detector_chs_s,
                irf=irf,
                period=period_ns,
                background=background,
                binning_factor=settings.micro_time_binning,
                micro_time_start=settings.micro_time_start,
                micro_time_stop=settings.micro_time_stop,
                min_photons=settings.min_photons,
                tau=settings.tau,
                gamma=settings.gamma,
                r0=settings.r0,
                rho=settings.rho,
                fix_tau=settings.fix_tau,
                fix_gamma=settings.fix_gamma,
                fix_r0=settings.fix_r0,
                fix_rho=settings.fix_rho,
                convolution_stop=-1,
                p2s_twoIstar=settings.twoi_star,
                soft_bifl_scatter=settings.bifl_scatter,
                engine=settings.engine,
                n_workers=settings.n_workers,
            )
            result = fit_pixel_lifetimes(tttr, core_settings)
            out_dir = request.output_dir or os.path.dirname(f)
            os.makedirs(out_dir, exist_ok=True)
            stem = os.path.splitext(os.path.basename(f))[0]
            out_path = os.path.join(out_dir, f"{stem}_pixel_mle.csv")
            result.dataframe.to_csv(out_path, index=False)
            processed.append(f)
            output_paths.append(out_path)

        return service_success(
            {
                "processed_files": processed,
                "output_paths": output_paths,
                "warnings": [],
            }
        )
    except Exception as exc:
        logger.exception("img_pixel_mle.analyze.run failed")
        return service_error(exc)


def _handle_contract(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the RPC contract descriptor."""
    return service_success(contract_descriptor())
