"""Headless CLI for per-pixel Number & Brightness."""

from __future__ import annotations

import click

from .. import core as _core


@click.command()
@click.argument("filename", type=click.Path(exists=True))
@click.option("--channel", "-c", multiple=True, type=int, default=(0,), help="Detector channel(s).")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output HDF5 path.")
@click.option(
    "--detrend",
    type=int,
    default=0,
    show_default=True,
    help="Segmented linear detrending: number of time segments (0 = off).",
)
@click.option(
    "--subtract",
    type=click.Choice(["none", "frame_mean", "pixel_mean", "moving_average"]),
    default="none",
    show_default=True,
    help="Stack correction subtracted first.",
)
@click.option(
    "--add",
    "add_back",
    type=click.Choice(["none", "total_mean", "frame_mean", "pixel_mean", "moving_average"]),
    default="none",
    show_default=True,
    help="Mean added back after subtracting.",
)
@click.option(
    "--box",
    type=(int, int),
    default=(3, 3),
    show_default=True,
    help="Moving-average box: pixels frames.",
)
@click.option(
    "--dead-time-ns", type=float, default=0.0, show_default=True, help="Detector dead time."
)
@click.option(
    "--pixel-dwell-us",
    type=float,
    default=0.0,
    show_default=True,
    help="Pixel dwell (needed by the dead-time correction).",
)
@click.option(
    "--gain",
    type=float,
    default=1.0,
    show_default=True,
    help="Analog gain S (1 = photon counting).",
)
@click.option("--offset", type=float, default=0.0, show_default=True, help="Analog offset.")
@click.option(
    "--read-variance",
    type=float,
    default=0.0,
    show_default=True,
    help="Analog read-noise variance.",
)
@click.option(
    "--gamma",
    type=float,
    default=1.0,
    show_default=True,
    help="Observation-volume shape factor (0.3536 = 1/sqrt(8), 3-D Gaussian).",
)
@click.option(
    "--smoothing",
    type=click.Choice(["none", "average", "disk", "gaussian"]),
    default="none",
    show_default=True,
    help="Moment smoothing.",
)
@click.option(
    "--radius", type=float, default=3.0, show_default=True, help="Moment smoothing radius."
)
@click.option("--median/--no-median", default=False, help="3x3 median filter on epsilon and n.")
def cli(
    filename,
    channel,
    output,
    detrend,
    subtract,
    add_back,
    box,
    dead_time_ns,
    pixel_dwell_us,
    gain,
    offset,
    read_variance,
    gamma,
    smoothing,
    radius,
    median,
):
    """Compute per-pixel N&B maps from a TTTR imaging FILENAME."""
    import numpy as np

    params = {
        "detrend_segments": detrend,
        "subtract": subtract,
        "add": add_back,
        "box_pixels": box[0],
        "box_frames": box[1],
        "dead_time": dead_time_ns,
        "pixel_dwell": pixel_dwell_us * 1000.0,
        "gain": gain,
        "offset": offset,
        "read_variance": read_variance,
        "gamma": gamma,
        "smoothing": smoothing,
        "radius": radius,
        "median": median,
    }
    result = _core.compute_nb(filename, channels=tuple(channel), params=params)
    maps = result["maps"]
    ny, nx = result["shape"]
    valid = maps["mean"] > 0
    click.echo(
        f"{nx}x{ny} px | B mean={np.mean(maps['B'][valid]):.3f} | "
        f"epsilon median={np.median(maps['epsilon'][valid]):.3f} | "
        f"n median={np.median(maps['n'][valid]):.3f}"
    )
    if output:
        _core.add_nb_to_hdf5(maps, output)
        click.echo(f"wrote {output}")


if __name__ == "__main__":
    cli()
