"""Click CLI for the synthetic decay generator (``synth-decay``)."""

from __future__ import annotations

import json

import click
import numpy as np

from ..core.algorithms import compute_aniso_decay, compute_component_decay, compute_decay


@click.group()
def cli() -> None:
    """Generate synthetic TCSPC fluorescence-decay histograms."""


def _write(result: dict, output: str | None, *, columns: tuple[str, ...] = ("x", "y"),
           header: str = "time_ns\tcounts") -> None:
    if output:
        if output.lower().endswith(".npy"):
            np.save(output, np.asarray(result[columns[1]], dtype=float))
        elif output.lower().endswith((".csv", ".txt", ".dat")):
            np.savetxt(
                output,
                np.column_stack([result[c] for c in columns]),
                header=header,
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


@cli.command()
@click.option("--lifetimes", required=True, help="Comma-separated lifetimes (ns), e.g. 1.2,4.0")
@click.option("--amplitudes", default=None, help="Comma-separated amplitudes (matches lifetimes).")
@click.option("--rotation", default="0.2,1.0", show_default=True,
              help="Comma-separated interleaved rotation spectrum (b,rho pairs), e.g. 0.3,2.0,0.1,10.")
@click.option("--g-factor", default=1.0, show_default=True, type=float,
              help="Parallel/perpendicular detection sensitivity ratio.")
@click.option("--l1", default=0.0, show_default=True, type=float, help="VV mixing factor.")
@click.option("--l2", default=0.0, show_default=True, type=float, help="VH mixing factor.")
@click.option("--n-bins", default=256, show_default=True, type=int)
@click.option("--bin-width", default=0.032, show_default=True, type=float, help="ns per bin.")
@click.option("--start-bin", default=0, show_default=True, type=int)
@click.option("--irf", "irf_path", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Optional IRF file (text or .npy) to convolve.")
@click.option("--photons", default=None, type=float,
              help="Poisson-sample this total photon budget across both channels.")
@click.option("--seed", default=None, type=int, help="Shot-noise seed.")
@click.option("--vvvh-file", "vvvh_path", default=None, type=click.Path(dir_okay=False),
              help="Also write the pair as a VV/VH file (.dat); the footer carries g/l1/l2.")
@click.option("--output", "-o", default=None, type=click.Path(dir_okay=False),
              help="Write to .json / .csv / .npy (default: print JSON).")
def aniso(lifetimes, amplitudes, rotation, g_factor, l1, l2, n_bins, bin_width,
          start_bin, irf_path, photons, seed, vvvh_path, output) -> None:
    """Generate a polarized VV/VH pair plus the anisotropy decay r(t).

    Output columns: time_ns, VV, VH, r(t). With --vvvh-file the two channels
    are additionally written in the VV/VH file format the reader consumes.
    """
    from chisurf.core.fio.vv_vh import write_vv_vh

    taus = [float(x) for x in str(lifetimes).split(",") if x.strip()]
    amps = [float(x) for x in str(amplitudes).split(",")] if amplitudes else None
    rot = [float(x) for x in str(rotation).split(",") if x.strip()]
    rot_rows = [{"b": rot[i], "rho": rot[i + 1]} for i in range(0, len(rot) - 1, 2)]
    result = compute_aniso_decay(
        n_bins=n_bins, lifetimes=taus, amplitudes=amps, rotation_rows=rot_rows,
        g_factor=g_factor, l1=l1, l2=l2, bin_width=bin_width, start_bin=start_bin,
        irf=irf_path, normalize=photons is None, photon_count=photons, seed=seed,
    )
    if vvvh_path:
        write_vv_vh(
            vvvh_path,
            vv=result["vv"], vh=result["vh"], g_factor=g_factor,
            metadata={"l1": l1, "l2": l2, "polarization": "vv/vh",
                      "dt_ns": bin_width, "source": "synth-decay aniso"},
        )
        click.echo(f"Wrote VV/VH file to {vvvh_path}")
    _write(
        {**result, "y": result["vv"]},
        output,
        columns=("x", "vv", "vh", "r"),
        header="time_ns\tVV\tVH\tr(t)",
    )


if __name__ == "__main__":  # pragma: no cover
    cli()
