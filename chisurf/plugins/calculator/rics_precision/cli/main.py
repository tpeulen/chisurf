"""Headless CLI for predicting the precision of a planned raster scan."""

from __future__ import annotations

import json

import click
import numpy as np

from .. import core as _core


@click.command()
@click.argument("diffusion_coefficient", type=float)
@click.option(
    "--pixel-time",
    "-t",
    type=float,
    default=None,
    help="Your intended pixel dwell time in µs; marked against the sweep.",
)
@click.option(
    "--pixel-size",
    type=float,
    default=50.0,
    show_default=True,
    help="Pixel size in nm. It should sample the waist 4-6 times over.",
)
@click.option("--w-r", type=float, default=0.25, show_default=True, help="Lateral waist in µm.")
@click.option("--w-z", type=float, default=1.25, show_default=True, help="Axial waist in µm.")
@click.option(
    "--n-particles",
    type=float,
    default=50.0,
    show_default=True,
    help="Molecules in the illuminated region.",
)
@click.option(
    "--brightness",
    type=float,
    default=100.0,
    show_default=True,
    help="Molecular brightness in kHz per molecule.",
)
@click.option("--nx", type=int, default=64, show_default=True, help="Pixels per line.")
@click.option("--ny", type=int, default=64, show_default=True, help="Lines per frame.")
@click.option(
    "--frames",
    type=int,
    default=100,
    show_default=True,
    help="Frames averaged. Precision improves as its square root.",
)
@click.option(
    "--line-overhead",
    type=float,
    default=1.2,
    show_default=True,
    help="How much longer a line takes than the sum of its pixels.",
)
@click.option("--membrane", is_flag=True, help="Use the 2-D (surface) geometry.")
@click.option(
    "--points",
    type=int,
    default=9,
    show_default=True,
    help="Dwell times swept, logarithmically from 0.5 µs to 0.5 ms.",
)
@click.option(
    "--n-lags",
    type=int,
    default=4,
    show_default=True,
    help="Largest lag fitted per axis. Cost grows as its fourth power.",
)
@click.option(
    "--repeats",
    type=int,
    default=40,
    show_default=True,
    help="Monte-Carlo realisations per point; the prediction itself "
    "carries a relative uncertainty of about 1/sqrt(2N).",
)
@click.option(
    "--seed",
    type=int,
    default=1,
    show_default=True,
    help="Random seed, so a quoted prediction can be reproduced.",
)
@click.option(
    "--out-csv", type=click.Path(), default=None, help="Write the swept prediction as CSV."
)
@click.option("--json", "as_json", is_flag=True, help="Print the summary as JSON.")
def cli(
    diffusion_coefficient,
    pixel_time,
    pixel_size,
    w_r,
    w_z,
    n_particles,
    brightness,
    nx,
    ny,
    frames,
    line_overhead,
    membrane,
    points,
    n_lags,
    repeats,
    seed,
    out_csv,
    as_json,
):
    """Predict how precisely a planned scan would measure DIFFUSION_COEFFICIENT.

    Takes no data: it answers from the settings you intend to use, before the
    microscope time is spent. The swept curve rises at both ends -- scan too
    fast and the molecule has not moved between neighbouring pixels, too slow
    and it has already decorrelated -- and the minimum between them is the dwell
    time that measures this D best.

    Read the optimum as an order of magnitude. Each point is itself a
    Monte-Carlo estimate, so along a flat stretch the argmin moves between
    neighbouring points from noise alone. Note also that the frame count is held
    fixed while the dwell is swept, so a slower scan here is also a longer
    acquisition -- the reported frame time is what makes that trade-off visible.
    """
    sweep = _core.sweep_dwell(
        float(diffusion_coefficient),
        _core.default_dwell_range(int(points)),
        nx=int(nx),
        line_overhead=float(line_overhead),
        current_dwell=(float(pixel_time) * 1e-6) if pixel_time else None,
        pixel_size=float(pixel_size) * 1e-3,
        ny=int(ny),
        n_particles=float(n_particles),
        w_r=float(w_r),
        w_z=float(w_z),
        brightness=float(brightness) * 1e3,
        n_images=int(frames),
        n_lags=int(n_lags),
        n_repeats=int(repeats),
        two_d=bool(membrane),
        seed=int(seed),
    )

    realisable = bool(np.isfinite(np.asarray(sweep.relative_error, dtype=float)).any())
    nothing_works = (
        "no dwell time is realisable with these settings — check the waists, the pixel size and D"
    )

    if out_csv:
        lines = ["dwell_us,line_ms,frame_ms,error_percent"]
        for dwell, line, err in zip(sweep.dwell, sweep.line_time, sweep.relative_error):
            error = "" if not np.isfinite(err) else f"{err * 100:.4g}"
            lines.append(f"{dwell * 1e6:.6g},{line * 1e3:.6g},{line * ny * 1e3:.6g},{error}")
        with open(out_csv, "w") as fh:
            fh.write("\n".join(lines) + "\n")

    if as_json:
        # A caller reading this payload has no other channel: a total failure has
        # to arrive as an error object and a non-zero status, not as a curve of
        # nulls under exit 0.
        if not realisable:
            click.echo(json.dumps({"error": nothing_works}, indent=2))
            click.get_current_context().exit(1)
        click.echo(json.dumps(sweep.to_dict(), indent=2))
        return

    if not realisable:
        raise click.ClickException(nothing_works)

    click.echo(f"D = {diffusion_coefficient:g} µm²/s, {nx}x{ny} px, {frames} frames")
    click.echo(f"{'dwell / µs':>12}{'frame / ms':>12}{'error / %':>12}")
    for dwell, line, err in zip(sweep.dwell, sweep.line_time, sweep.relative_error):
        error = "—" if not np.isfinite(err) else f"{err * 100:.1f}"
        click.echo(f"{dwell * 1e6:>12.3g}{line * ny * 1e3:>12.3g}{error:>12}")

    click.echo(
        f"\nbest around {sweep.best_dwell * 1e6:.3g} µs at {sweep.best_error * 100:.1f} % error"
    )
    if sweep.current is not None:
        here = sweep.current.relative_error
        gain = here / sweep.best_error if sweep.best_error > 0 else float("nan")
        click.echo(f"your {pixel_time:g} µs: {here * 100:.1f} % error, {gain:.1f}x the best")


if __name__ == "__main__":
    cli()
