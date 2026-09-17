"""Headless CLI for single-particle tracking."""

from __future__ import annotations

import json
import pathlib

import click

from chisurf.core.fluorescence.imaging import tracking as tk

from .. import core as _core


@click.command("img-tracking")
@click.argument("image", type=click.Path(exists=True), required=False)
@click.option("--channel", type=int, default=0, help="Channel to track in.")
@click.option("--max-frames", type=int, default=0, help="Track at most this many frames.")
@click.option(
    "--pixel-size",
    type=float,
    default=1.0,
    help="Pixel size in um; 1 reports D in pixels squared per frame.",
)
@click.option(
    "--frame-interval",
    type=float,
    default=1.0,
    help="Frame interval in seconds; 1 reports D per frame.",
)
@click.option(
    "--method", type=click.Choice(["wavelet", "quantile"]), default="wavelet", help="Detector."
)
@click.option(
    "--threshold",
    type=float,
    default=5.0,
    help="Detection threshold in robust standard deviations.",
)
@click.option("--min-area", type=int, default=2, help="Smallest region that can be a particle.")
@click.option(
    "--min-separation", type=float, default=3.0, help="Closest two particles may be in one frame."
)
@click.option(
    "--max-distance",
    type=float,
    default=5.0,
    help="Largest per-frame displacement that is still the same particle.",
)
@click.option("--max-gap", type=int, default=1, help="Missing frames a track may bridge.")
@click.option(
    "--min-track-length", type=int, default=10, help="Shortest track admitted to the transport fit."
)
@click.option(
    "--fit-alpha",
    is_flag=True,
    help="Fit the anomalous exponent as well as D. Off by default: the two are "
    "nearly degenerate and fitting both greatly widens D.",
)
@click.option("--bootstrap", type=int, default=200, help="Track resamples behind the error bars.")
@click.option(
    "--simulate", is_flag=True, help="Track a simulated movie with a known D instead of a file."
)
@click.option("--sim-diffusion", type=float, default=0.5, help="True D of the simulation.")
@click.option("--sim-particles", type=int, default=8, help="Simulated particles.")
@click.option("--sim-frames", type=int, default=60, help="Simulated frames.")
@click.option("--sim-size", type=int, default=256, help="Simulated field size in pixels.")
@click.option("--sim-seed", type=int, default=1, help="Simulation seed.")
@click.option("--as-json", is_flag=True, help="Print the whole result as JSON.")
@click.option(
    "--tracks-csv",
    type=click.Path(),
    default=None,
    help="Write every linked detection to this CSV file.",
)
@click.option(
    "--output", "-o", type=click.Path(), default=None, help="Write the result as JSON to this file."
)
def cli(
    image,
    channel,
    max_frames,
    pixel_size,
    frame_interval,
    method,
    threshold,
    min_area,
    min_separation,
    max_distance,
    max_gap,
    min_track_length,
    fit_alpha,
    bootstrap,
    simulate,
    sim_diffusion,
    sim_particles,
    sim_frames,
    sim_size,
    sim_seed,
    as_json,
    tracks_csv,
    output,
):
    """Detect, link and analyse single particles in an image stack.

    Finds diffraction-limited particles in every frame, links them into
    trajectories, and fits the diffusion coefficient and anomalous exponent from
    the mean squared displacement. With ``--simulate`` it needs no data at all,
    which is the quickest way to see what a given frame rate and particle
    density can resolve.
    """
    if simulate:
        try:
            frames, _ = tk.simulate_particle_movie(
                n_frames=sim_frames,
                shape=(sim_size, sim_size),
                n_particles=sim_particles,
                diffusion_coefficient=sim_diffusion,
                seed=sim_seed,
            )
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc
        info = {
            "source": "simulation",
            "n_frames": sim_frames,
            "true_diffusion": sim_diffusion,
            "n_particles": sim_particles,
        }
    else:
        if not image:
            raise click.UsageError("give an image stack, or use --simulate")
        try:
            frames, info = _core.load_frames(image, channel=channel, max_frames=max_frames)
        except Exception as exc:
            if as_json:
                click.echo(json.dumps({"error": str(exc)}))
            else:
                click.echo(f"Could not load {image}: {exc}", err=True)
            raise SystemExit(1) from exc

    result = _core.analyse(
        frames,
        pixel_size=pixel_size,
        frame_interval=frame_interval,
        method=method,
        threshold=threshold,
        min_area=min_area,
        min_separation=min_separation,
        max_distance=max_distance,
        max_frame_gap=max_gap,
        min_track_length=min_track_length,
        fix_alpha=None if fit_alpha else 1.0,
        n_bootstrap=bootstrap,
        info=info,
    )

    if tracks_csv:
        result.write_csv(tracks_csv)
    payload = result.to_dict()
    if output:
        pathlib.Path(output).write_text(json.dumps(payload, indent=2) + "\n")
    if as_json:
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(result.report())
        if tracks_csv:
            click.echo(f"\nWrote {tracks_csv}")
        if output:
            click.echo(f"Wrote {output}")
    # A run that produced no transport fit is not a success for a pipeline.
    if result.fit is None:
        raise SystemExit(2)


__all__ = ["cli"]
