"""CLI for molecule-wise MLE lifetime analysis of TTTR imaging data.

Usage::

    sm-image-mle analyze --irf-file IRF.ptu FILE [FILE …]
    sm-image-mle contract
    sm-image-mle serve
"""

from __future__ import annotations

import json

import click


@click.group()
def cli() -> None:
    """Molecule-wise MLE lifetime analysis for TTTR imaging data."""


@cli.command()
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--irf-file", "-i", required=True, type=click.Path(exists=True), help="IRF PTU file.")
@click.option("--output-dir", "-o", default="", help="Override output directory for the joint TSV.")
@click.option(
    "--detector-chs", default="0,1", help="Detector channels (comma-separated; even=∥, odd=⊥)."
)
@click.option(
    "--micro-time-range", default="0,256", help="Fit window on the binned axis as 'start,stop'."
)
@click.option("--micro-time-binning", default=1, type=int, help="Micro-time down-binning factor.")
@click.option("--normalize-counts", default=0, type=int, help="VV/VH normalisation mode (0-3).")
@click.option(
    "--threshold", default=-1.0, type=float, help="VV/VH threshold fraction (<=0 disables)."
)
@click.option("--shift-sp", default=0.0, type=float, help="Parallel IRF shift (channels).")
@click.option("--shift-ss", default=0.0, type=float, help="Perpendicular IRF shift (channels).")
@click.option(
    "--irf-threshold-fraction", default=0.08, type=float, help="IRF denoising threshold fraction."
)
@click.option("--tau", default=2.0, type=float, help="Initial lifetime (ns).")
@click.option("--gamma", default=0.0, type=float, help="Initial scatter fraction.")
@click.option("--r0", default=0.38, type=float, help="Initial fundamental anisotropy.")
@click.option("--rho", default=1.0, type=float, help="Initial rotational correlation time (ns).")
@click.option("--fix-tau/--free-tau", default=False, help="Fix the lifetime.")
@click.option("--fix-gamma/--free-gamma", default=False, help="Fix the scatter fraction.")
@click.option("--fix-r0/--free-r0", default=True, help="Fix the fundamental anisotropy.")
@click.option("--fix-rho/--free-rho", default=False, help="Fix the rotational correlation time.")
@click.option("--l1", default=0.0, type=float, help="Polarisation mixing correction l1.")
@click.option("--l2", default=0.0, type=float, help="Polarisation mixing correction l2.")
@click.option("--twoi-star/--no-twoi-star", default=True, help="Optimise P+2S (2I*).")
@click.option("--bifl-scatter/--no-bifl-scatter", default=False, help="Soft BIFL scatter.")
@click.option("--seg-sigma", default=1.0, type=float, help="Segmentation Gaussian sigma.")
@click.option(
    "--seg-threshold", default=-1.0, type=float, help="Segmentation threshold (<0 = Otsu)."
)
@click.option("--peak-footprint-size", default=6, type=int, help="Peak-detection footprint size.")
@click.option("--min-area", default=1, type=int, help="Minimum molecule area (pixels).")
@click.option("--min-photons", default=1, type=int, help="Minimum photons per molecule to fit.")
@click.option(
    "--roi",
    # None, not "": click validates the default against the Path type, and an
    # empty string is not an existing file.
    default=None,
    type=click.Path(exists=True, dir_okay=False),
    help=(
        "Analysis region: a saved ROI JSON, a mask image or a label image. "
        "Molecules are searched only inside it, and an automatic threshold is "
        "computed from its pixels alone. Several regions in one file are unioned."
    ),
)
@click.option("--json", "json_output", is_flag=True, help="Print the result as JSON.")
def analyze(
    files,
    irf_file,
    output_dir,
    detector_chs,
    micro_time_range,
    micro_time_binning,
    normalize_counts,
    threshold,
    shift_sp,
    shift_ss,
    irf_threshold_fraction,
    tau,
    gamma,
    r0,
    rho,
    fix_tau,
    fix_gamma,
    fix_r0,
    fix_rho,
    l1,
    l2,
    twoi_star,
    bifl_scatter,
    seg_sigma,
    seg_threshold,
    peak_footprint_size,
    min_area,
    min_photons,
    roi,
    json_output,
) -> None:
    """Analyze CLSM imaging FILES with molecule-wise MLE."""
    from ..api.models import MoleculeMleRequest, MoleculeMleSettings
    from ..api.molecule_mle import analyze_request

    det_chs = [int(c.strip()) for c in detector_chs.split(",") if c.strip()]
    mtr = tuple(int(x.strip()) for x in micro_time_range.split(","))

    # A region file may hold one region, several, or a whole segmentation; the
    # analysis takes a single region, so several become their union.
    analysis_roi = None
    if roi:
        from chisurf.core.roi import load_region

        analysis_roi = load_region(roi).to_dict()

    settings = MoleculeMleSettings(
        detector_chs=det_chs,
        micro_time_range=(mtr[0], mtr[1]),
        micro_time_binning=micro_time_binning,
        normalize_counts=normalize_counts,
        threshold=threshold,
        tau=tau,
        gamma=gamma,
        r0=r0,
        rho=rho,
        fix_tau=fix_tau,
        fix_gamma=fix_gamma,
        fix_r0=fix_r0,
        fix_rho=fix_rho,
        l1=l1,
        l2=l2,
        p2s_twoIstar=twoi_star,
        soft_bifl_scatter=bifl_scatter,
        seg_sigma=seg_sigma,
        seg_threshold=seg_threshold,
        peak_footprint_size=peak_footprint_size,
        min_area=min_area,
        min_photons=min_photons,
        roi=analysis_roi,
    )
    request = MoleculeMleRequest(
        files=list(files),
        irf_file=irf_file,
        output_dir=output_dir,
        settings=settings,
        shift_sp=shift_sp,
        shift_ss=shift_ss,
        irf_threshold_fraction=irf_threshold_fraction,
    )

    click.echo(f"Analyzing {len(files)} file(s)…")
    result = analyze_request(request)

    if json_output:
        import dataclasses

        click.echo(json.dumps(dataclasses.asdict(result), indent=2))
    else:
        click.echo(f"Processed: {result.processed_files}")
        click.echo(f"Molecules fitted: {result.n_molecules}")
        click.echo(f"Output TSVs: {result.output_paths}")
        if result.joint_tsv:
            click.echo(f"Joint TSV: {result.joint_tsv}")
        for w in result.warnings:
            click.echo(f"WARNING: {w}", err=True)


@cli.command()
@click.option("--json", "json_output", is_flag=True, help="Print as JSON.")
def contract(json_output: bool) -> None:
    """Print the RPC contract descriptor."""
    from ..api.contract import contract_descriptor

    desc = contract_descriptor()
    if json_output:
        click.echo(json.dumps(desc, indent=2))
    else:
        click.echo(f"Plugin: {desc['plugin_id']} v{desc['version']}")
        click.echo(f"Methods: {', '.join(desc['methods'])}")


@cli.command()
@click.option("--host", default="127.0.0.1", help="ZMQ bind host.")
@click.option("--port", default=5555, type=int, help="ZMQ bind port.")
def serve(host: str, port: int) -> None:
    """Start the sm_image_mle RPC service (ZMQ/JSON-RPC)."""
    click.echo(f"Starting sm_image_mle service on {host}:{port} …")
    try:
        from chisurf.server.dispatcher import ServiceDispatcher
        from chisurf.server.session import SessionState

        from ..backend.services import register_services

        state = SessionState()
        dispatcher = ServiceDispatcher(state)
        register_services(dispatcher)
        click.echo("Services registered. Listening…")
        dispatcher.serve(host=host, port=port)
    except Exception as exc:
        click.echo(f"Failed to start service: {exc}", err=True)
        raise SystemExit(1) from exc
