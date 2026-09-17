"""Headless CLI: map the velocity field of an image stack or photon stream."""

from __future__ import annotations

import json

import click

from ..client import FlowClient


@click.group()
def cli():
    """Flow maps: where a sample is moving, and how fast.

    A velocity is read off where a correlation peak *is*, not off a parameter
    released in a transport model, so there is nothing to fit and nothing to
    initialise. Start from ``img-flow demo`` if you have never seen one: it
    simulates a scan whose flow profile is known, so the arrows can be checked.
    """


@cli.command("map")
@click.argument("filename", type=click.Path(exists=True))
@click.option(
    "--method",
    type=click.Choice(["stics", "pcf"]),
    default="stics",
    show_default=True,
    help="Track the peak's position (stics) or its arrival time (pcf).",
)
@click.option(
    "--channel", "-c", default="0", show_default=True, help="Image channel, by index or by name."
)
@click.option(
    "--tile",
    type=int,
    default=24,
    show_default=True,
    help="Tile size in pixels — the spatial resolution of the map.",
)
@click.option(
    "--step", type=int, default=0, help="Distance between tile origins (default: half a tile)."
)
@click.option(
    "--lags",
    "n_lags",
    type=int,
    default=5,
    show_default=True,
    help="STICS: frame lags 0..N-1. The peak must stay inside the tile.",
)
@click.option(
    "--distance", type=int, default=4, show_default=True, help="pCF: pair distance in pixels."
)
@click.option(
    "--pixel-dwell",
    "pixel_duration_us",
    type=float,
    default=20.0,
    show_default=True,
    help="Pixel dwell in microseconds.",
)
@click.option(
    "--line-time",
    "line_duration_ms",
    type=float,
    default=0.0,
    help="Line time in ms (default: pixels per line x dwell).",
)
@click.option(
    "--frame-time",
    "frame_duration_ms",
    type=float,
    default=0.0,
    help="Frame time in ms (default: lines x line time).",
)
@click.option(
    "--pixel-size",
    "pixel_size_nm",
    type=float,
    default=100.0,
    show_default=True,
    help="Pixel size in nm; it scales every velocity.",
)
@click.option(
    "--subtract",
    "subtract_average",
    type=click.Choice(["frame", "stack", ""]),
    default="frame",
    show_default=True,
    help="'stack' also removes the time-average, i.e. the immobile part.",
)
@click.option(
    "--min-quality",
    type=float,
    default=0.5,
    show_default=True,
    help="Drop tiles whose straight-line fit is worse than this.",
)
@click.option(
    "--out-csv",
    "output_path",
    type=click.Path(),
    default=None,
    help="Write one row per kept tile to a CSV file.",
)
@click.option("--json", "as_json", is_flag=True, help="Print the result as JSON.")
def map_command(filename, as_json, **kwargs):
    """Map the velocity field of FILENAME (a TIFF stack or a photon stream)."""
    try:
        result = FlowClient().flow_map(filename, **kwargs)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    summary = result["summary"]
    click.echo(f"{filename} — {result['method']}, {result['shape'][0]}x{result['shape'][1]} tiles")
    kept, total = int(summary["n_kept"]), int(summary["n_tiles"])
    click.echo(f"kept {kept}/{total} tiles at quality >= {result['min_quality']}")
    if result["n_escaped"]:
        click.echo(
            f"REFUSED {result['n_escaped']} tile(s): the correlation peak left the "
            "tile, where it wraps around and fits a confident backwards velocity. "
            "Use fewer lags or a larger tile."
        )
    if not kept:
        raise click.ClickException(
            "no tile passed the quality threshold — either the sample is not "
            "moving, or the flow is too slow to shift the peak over this lag range"
        )
    click.echo(f"mean speed: {summary['mean_speed']:.4g} um/s")
    click.echo(
        f"mean vector: ({summary['mean_vx']:.4g}, {summary['mean_vy']:.4g}) um/s"
        f" at {summary['angle_deg']:.1f} deg"
    )
    click.echo(
        f"coherence: {summary['coherence']:.2f}"
        " (1 = one direction everywhere, 0 = arrows at random)"
    )
    if result.get("output_path"):
        click.echo(f"wrote {result['output_path']}")


@cli.command("demo")
@click.option(
    "--path",
    type=click.Path(),
    default=None,
    help="Where to write it (default: the ChiSurf settings directory).",
)
@click.option("--overwrite", is_flag=True, help="Regenerate even if it exists.")
@click.option("--frames", "n_frames", type=int, default=None, help="Frames to scan.")
@click.option("--json", "as_json", is_flag=True, help="Print the result as JSON.")
def demo_command(path, overwrite, n_frames, as_json):
    """Simulate a photon stream whose flow profile is known, and write it as PTU.

    Laminar flow through a channel: fastest in the middle, zero at the walls.
    Everything the tool reports can therefore be checked against a number, which
    is the only honest way to learn what a flow map does and does not measure.
    """
    kwargs = {"overwrite": overwrite}
    if path:
        kwargs["path"] = path
    if n_frames:
        kwargs["n_frames"] = n_frames
    try:
        result = FlowClient().demo(**kwargs)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return
    truth, timing = result["truth"], result["timing"]
    click.echo(("wrote " if result["created"] else "already there: ") + result["path"])
    click.echo(
        f"true flow: {truth['profile']} along {truth['axis']}, "
        f"peak {truth['v_max_um_s']} um/s, D = "
        f"{truth['diffusion_coefficient_um2_s']} um^2/s"
    )
    click.echo(
        f"timing: dwell {timing['pixel_duration_us']:.1f} us, frame "
        f"{timing['frame_duration_ms']:.1f} ms, pixel "
        f"{timing['pixel_size_nm']:.0f} nm"
    )
    click.echo(
        f"the peak moves {truth['peak_shift_px_per_frame']:.2f} px per frame "
        "at the channel centre — which is what bounds the usable lag range"
    )


@cli.command("methods")
def methods_command():
    """List the estimators and what each of them can and cannot see."""
    result = FlowClient().methods()
    for name in result["methods"]:
        click.echo(f"{name}: {result['labels'][name]}")
        click.echo(f"    {result['notes'][name]}")


if __name__ == "__main__":
    cli()
