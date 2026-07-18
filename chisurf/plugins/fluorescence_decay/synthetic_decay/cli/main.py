"""Click CLI for the synthetic decay generator (``synth-decay``)."""

from __future__ import annotations

import json

import click
import numpy as np

from ..core.algorithms import compute_component_decay, compute_decay


@click.group()
def cli() -> None:
    """Generate synthetic TCSPC fluorescence-decay histograms."""


def _write(result: dict, output: str | None) -> None:
    if output:
        if output.lower().endswith(".npy"):
            np.save(output, np.asarray(result["y"], dtype=float))
        elif output.lower().endswith((".csv", ".txt", ".dat")):
            np.savetxt(
                output,
                np.column_stack([result["x"], result["y"]]),
                header="time_ns\tcounts",
            )
        else:
            with open(output, "w") as fh:
                json.dump(result, fh, indent=2)
        click.echo(f"Wrote {result['n_bins']} bins to {output}")
    else:
        click.echo(json.dumps(result, indent=2))


@cli.command()
@click.option("--lifetimes", required=True, help="Comma-separated lifetimes (ns), e.g. 1.2,4.0")
@click.option("--amplitudes", default=None, help="Comma-separated amplitudes (matches lifetimes).")
@click.option("--n-bins", default=256, show_default=True, type=int)
@click.option("--bin-width", default=0.032, show_default=True, type=float, help="ns per bin.")
@click.option("--start-bin", default=0, show_default=True, type=int)
@click.option("--irf", "irf_path", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Optional IRF file (text or .npy) to convolve.")
@click.option("--photons", default=None, type=float, help="Poisson-sample to this photon count.")
@click.option("--seed", default=None, type=int, help="Shot-noise seed.")
@click.option("--no-normalize", is_flag=True, help="Do not normalize the output to unit sum.")
@click.option("--output", "-o", default=None, type=click.Path(dir_okay=False),
              help="Write to .json / .csv / .npy (default: print JSON).")
def generate(lifetimes, amplitudes, n_bins, bin_width, start_bin, irf_path,
             photons, seed, no_normalize, output) -> None:
    """Generate a decay from lifetimes (+ optional amplitudes, IRF, shot noise)."""
    taus = [float(x) for x in str(lifetimes).split(",") if x.strip()]
    amps = [float(x) for x in str(amplitudes).split(",")] if amplitudes else None
    result = compute_decay(
        n_bins=n_bins, lifetimes=taus, amplitudes=amps, bin_width=bin_width,
        start_bin=start_bin, irf=irf_path, normalize=not no_normalize,
        photon_count=photons, seed=seed,
    )
    _write(result, output)


@cli.command()
@click.argument("component_json", type=click.Path(exists=True, dir_okay=False))
@click.option("--n-bins", default=256, show_default=True, type=int)
@click.option("--irf", "irf_path", default=None, type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", default=None, type=click.Path(dir_okay=False))
def component(component_json, n_bins, irf_path, output) -> None:
    """Generate a decay from a component-definition JSON file."""
    with open(component_json) as fh:
        comp = json.load(fh)
    result = compute_component_decay(n_bins=n_bins, component=comp, irf=irf_path)
    _write(result, output)


if __name__ == "__main__":  # pragma: no cover
    cli()
