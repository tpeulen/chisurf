"""Headless CLI for per-pixel phasor-FLIM."""

from __future__ import annotations

import click

from .. import core as _core


@click.command()
@click.argument("filename", type=click.Path(exists=True))
@click.option("--channel", "-c", multiple=True, type=int, default=(0,), help="Detector channel(s).")
@click.option("--frequency", "-f", type=float, default=-1.0, help="Modulation frequency (MHz); -1 = auto.")
@click.option("--irf", type=click.Path(exists=True), default=None, help="Reference/IRF TTTR file.")
@click.option("--n-ph-min", type=int, default=3, help="Minimum photons per pixel.")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output HDF5 path.")
def cli(filename, channel, frequency, irf, n_ph_min, output):
    """Compute per-pixel phasor (g, s) maps from a TTTR imaging FILENAME."""
    import numpy as np

    result = _core.compute_phasor(
        filename, channels=tuple(channel), frequency=frequency,
        irf_filename=irf, n_ph_min=n_ph_min,
    )
    maps = result["maps"]
    ny, nx = result["shape"]
    m = maps.get("n_photons", np.ones_like(maps["g"])) > 0
    click.echo(f"{nx}x{ny} px | g mean={np.nanmean(maps['g'][m]):.3f} | s mean={np.nanmean(maps['s'][m]):.3f}")

    # Derived apparent-lifetime maps require an explicit modulation frequency.
    if frequency > 0.0:
        maps = _core.derived_phasor_maps(maps, frequency)
        click.echo(
            f"derived @ {frequency:g} MHz | "
            f"tau_phi mean={np.nanmean(maps['tau_phi'][m]):.3f} ns | "
            f"tau_m mean={np.nanmean(maps['tau_m'][m]):.3f} ns"
        )
    else:
        click.echo("(pass --frequency > 0 for apparent-lifetime maps)")

    if output:
        _core.add_phasor_to_hdf5(maps, output)
        click.echo(f"wrote {output}")


if __name__ == "__main__":
    cli()
