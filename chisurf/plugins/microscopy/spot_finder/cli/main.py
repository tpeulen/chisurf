"""CLI for spot and region detection in imaging data.

Usage::

    spot-finder detect --method log FILE [FILE …]
    spot-finder list FILE
    spot-finder contract
"""

from __future__ import annotations

import dataclasses
import json

import click


@click.group()
def cli() -> None:
    """Detect spots and regions in imaging data, and persist what was found."""


@cli.command()
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--method", default="watershed",
              type=click.Choice(["watershed", "threshold", "log", "dog"]),
              help="Detector. watershed splits touching objects; log/dog measure width.")
@click.option("--name", default="spots", help="Stem the raster/table pair is written under.")
@click.option("--sigma", default=1.0, type=float, help="Pre-threshold Gaussian smoothing.")
@click.option("--threshold", default=-1.0, type=float,
              help="Intensity level (<0 = Otsu); for log/dog, the minimum response.")
@click.option("--peak-footprint-size", default=6, type=int,
              help="Watershed seed footprint; larger merges nearby seeds.")
@click.option("--min-area", default=2, type=int, help="Smallest region to keep (pixels).")
@click.option("--max-area", default=0, type=int, help="Largest region to keep; 0 disables.")
@click.option("--clear-border/--keep-border", default=True,
              help="Drop regions touching the frame edge.")
@click.option("--min-sigma", default=1.0, type=float, help="Smallest spot width (log/dog).")
@click.option("--max-sigma", default=5.0, type=float, help="Largest spot width (log/dog).")
@click.option("--num-sigma", default=10, type=int, help="Scales between them (log).")
@click.option("--overlap", default=0.5, type=float, help="Blob merge threshold (log/dog).")
@click.option("--roi", "roi_path", default="", type=click.Path(),
              help="Confine the search: a saved region JSON, a mask or a label image.")
@click.option("--channels", default="", help="Routing channels for a photon file, comma-separated.")
@click.option("--frame", default=-1, type=int, help="Frame to detect in; -1 sums over frames.")
@click.option("--dry-run", is_flag=True, help="Detect and report, writing nothing.")
@click.option("--out-dir", default="", help="Directory for the containers.")
@click.option("--json", "json_output", is_flag=True, help="Print the run table as JSON.")
def detect(files, method, name, sigma, threshold, peak_footprint_size, min_area,
           max_area, clear_border, min_sigma, max_sigma, num_sigma, overlap,
           roi_path, channels, frame, dry_run, out_dir, json_output) -> None:
    """Detect regions in FILES and write each into its measurement's container."""
    from ..api.models import SpotFinderRequest, SpotFinderSettings
    from ..api.spot_finder import detect_request

    analysis_roi = None
    if roi_path:
        from chisurf.core.roi.io import load_region

        # Several regions arriving as their union, which is what a saved
        # multi-region file means when it is used as an analysis area.
        analysis_roi = load_region(roi_path)

    settings = SpotFinderSettings(
        method=method,
        sigma=sigma,
        threshold=threshold,
        peak_footprint_size=peak_footprint_size,
        min_area=min_area,
        max_area=max_area,
        clear_border=clear_border,
        min_sigma=min_sigma,
        max_sigma=max_sigma,
        num_sigma=num_sigma,
        overlap=overlap,
        roi=analysis_roi,
    )
    request = SpotFinderRequest(
        files=list(files),
        name=name,
        channels=[int(c) for c in channels.split(",") if c.strip()] or None,
        frame=frame,
        settings=settings,
        write=not dry_run,
        out_dir=out_dir,
    )

    result = detect_request(
        request,
        progress=None if json_output else _echo_progress,
    )

    if json_output:
        click.echo(json.dumps(
            {"rows": [dataclasses.asdict(r) for r in result.rows],
             "n_regions": result.n_regions}, indent=2))
    else:
        for row in result.rows:
            suffix = f" — {row.reason}" if row.reason else ""
            click.echo(f"{row.status:<8}{row.n_regions:>7}  {row.input}{suffix}")
        click.echo(f"{result.n_regions} region(s) in {len(result.ok)}/{len(result.rows)} file(s)")

    # Non-zero when nothing was detected anywhere: a batch that found nothing is
    # a batch a script should notice, and "it ran" is not the same as "it worked".
    if not result.ok:
        raise SystemExit(1)


@cli.command(name="list")
@click.argument("file", type=click.Path(exists=True))
def list_detections(file) -> None:
    """List the detections held in FILE's container."""
    from chisurf.core.fio.fluorescence.region_container import (
        list_region_sets,
        read_regions,
    )

    names = list_region_sets(file)
    if not names:
        click.echo("no detections")
        raise SystemExit(1)
    for name in names:
        regions = read_regions(file, name=name)
        click.echo(f"{name}: {regions.n_regions} region(s)")


@cli.command()
@click.option("--json", "json_output", is_flag=True, help="Print as JSON.")
def contract(json_output: bool) -> None:
    """Print the RPC contract."""
    from ..api.contract import contract_descriptor

    descriptor = contract_descriptor()
    if json_output:
        click.echo(json.dumps(descriptor, indent=2))
    else:
        for method in descriptor.get("methods", []):
            click.echo(method)


def _echo_progress(index: int, total: int, name: str) -> None:
    click.echo(f"[{index + 1}/{total}] {name}", err=True)
