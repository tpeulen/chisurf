"""Command-line interface for 2D fluorescence lifetime correlation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import numpy as np

from .. import api


@click.group()
def cli() -> None:
    """Run 2D-FLCS analysis tasks."""


@cli.command("metadata")
@click.argument("tttr_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--routing", type=int, multiple=True, help="Routing channel to keep. Repeatable.")
@click.option("--output", "-o", type=click.Path(dir_okay=False), help="Optional JSON output path.")
def metadata(tttr_file: str, routing: tuple[int, ...], output: str | None) -> None:
    """Load TTTR metadata used by 2D-FLCS."""
    try:
        data = api.load_tttr(tttr_file, routing_channels=routing or None)
        payload = {
            "path": str(Path(tttr_file)),
            "n_photons": int(data.n_photons),
            "macro_time_resolution_s": float(data.macro_time_resolution_s),
            "micro_time_resolution_ns": float(data.micro_time_resolution_ns),
            "n_microtime_channels": int(data.n_microtime_channels),
        }
        _emit_json(payload, output)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.command("lifetime")
@click.argument("tttr_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--routing", type=int, multiple=True, help="Routing channel to keep. Repeatable.")
@click.option("--tau-min", default=0.3, show_default=True, type=float, help="Minimum lifetime in ns.")
@click.option("--tau-max", default=8.0, show_default=True, type=float, help="Maximum lifetime in ns.")
@click.option("--components", default=40, show_default=True, type=int, help="Lifetime grid size.")
@click.option(
    "--method",
    default="nnls",
    show_default=True,
    type=click.Choice(["nnls", "tikhonov"]),
    help="1D inverse-Laplace solver.",
)
@click.option("--output", "-o", type=click.Path(dir_okay=False), help="Optional JSON output path.")
def lifetime(
    tttr_file: str,
    routing: tuple[int, ...],
    tau_min: float,
    tau_max: float,
    components: int,
    method: str,
    output: str | None,
) -> None:
    """Resolve a 1D lifetime distribution from a TTTR file."""
    try:
        data = api.load_tttr(tttr_file, routing_channels=routing or None)
        result = api.lifetime_spectrum(
            data.micro_times,
            data.n_microtime_channels,
            data.micro_time_resolution_ns,
            tau_range=(tau_min, tau_max),
            n_components=components,
            method=method,
        )
        payload = {
            "path": str(Path(tttr_file)),
            "tau_grid": result.tau_grid.tolist(),
            "amplitudes": result.amplitudes.tolist(),
            "peak_lifetimes": result.peak_lifetimes(2).tolist(),
            "chi2": float(result.chi2),
        }
        _emit_json(payload, output)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.command("reproduce")
@click.argument("params_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", type=click.Path(dir_okay=False), help="Optional JSON output path.")
def reproduce(params_file: str, output: str | None) -> None:
    """Rebuild the decay or 2D-FDC/2D-FLC maps from fitted parameters (JSON).

    PARAMS_FILE holds ``time_axis_ns``, ``tau_grid`` and ``amplitudes``: a list is a 1D
    distribution (1D-FDC), an ``n_comp x n_states`` table goes with ``correlation``
    (``s x s``, or one per lag) for the 2D maps. Optional: ``y0``, ``irf``,
    ``irf_time_ns``, ``data`` (and ``data_cor``), ``mi``, ``regulator``.
    """
    try:
        p = json.loads(Path(params_file).read_text())
        arr = {
            k: (None if p.get(k) is None else np.asarray(p[k], dtype=float))
            for k in ("irf", "irf_time_ns", "data", "data_cor", "mi")
        }
        common = dict(
            tau_grid=np.asarray(p["tau_grid"], float),
            irf=arr["irf"],
            irf_time_ns=arr["irf_time_ns"],
            mi=arr["mi"],
            regulator=p.get("regulator"),
        )
        axis = np.asarray(p["time_axis_ns"], float)
        amplitudes = np.asarray(p["amplitudes"], float)
        if "correlation" in p:
            res = api.reproduce_2d_fdc(
                amplitudes,
                np.asarray(p["correlation"], float),
                axis,
                y0=p.get("y0", 0.0),
                matrix=arr["data"],
                matrix_cor=arr["data_cor"],
                **common,
            )
        else:
            res = api.reproduce_1d_fdc(
                amplitudes,
                axis,
                y0=float(p.get("y0", 0.0)),
                decay=arr["data"],
                decay_cor=arr["data_cor"],
                **common,
            )
        payload = {
            "model": np.asarray(res.model).tolist(),
            "flc_map": None if res.flc_map is None else np.asarray(res.flc_map).tolist(),
            "chi2": res.chi2,
            "entropy": res.entropy,
            "estimator_q": res.estimator_q,
        }
        _emit_json(payload, output)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.command("bootstrap")
@click.argument("tttr_files", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--dt",
    "dt_ticks",
    type=int,
    multiple=True,
    required=True,
    help="Lag in macro ticks. Repeatable; the longest is the background.",
)
@click.option(
    "--ddt", "ddt_ticks", type=int, required=True, help="Lag window in macro ticks (even)."
)
@click.option("--tmin", type=int, required=True, help="Micro-time gate start (channels).")
@click.option("--tmax", type=int, required=True, help="Micro-time gate end (channels).")
@click.option("--routing", type=int, multiple=True, help="Routing channel to keep. Repeatable.")
@click.option("--lin-factor", default=4, show_default=True, type=int, help="Linear bin factor.")
@click.option("--log-bins", default=100, show_default=True, type=int, help="Number of log bins.")
@click.option(
    "--replicates", default=100, show_default=True, type=int, help="Bootstrap replicates."
)
@click.option(
    "--group-factor",
    default=2,
    show_default=True,
    type=int,
    help="Times each molecule may be drawn per replicate.",
)
@click.option(
    "--photon-factor",
    default=1.0,
    show_default=True,
    type=float,
    help="Photons per replicate, as a multiple of the data set's.",
)
@click.option("--seed", type=int, default=None, help="Random seed.")
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False),
    required=True,
    help="NPZ with the summed matrices and their bootstrap mean and std.",
)
def bootstrap(
    tttr_files,
    dt_ticks,
    ddt_ticks,
    tmin,
    tmax,
    routing,
    lin_factor,
    log_bins,
    replicates,
    group_factor,
    photon_factor,
    seed,
    output,
) -> None:
    """Per-molecule 2D-FDC (one TTTR file per molecule) with bootstrap error bars."""
    try:
        molecules = []
        for f in tttr_files:
            data = api.load_tttr(f, routing_channels=routing or None)
            molecules.append((data.macro_times, data.micro_times))
        sep = api.separate_data_2d_fdc(
            molecules,
            list(dt_ticks),
            ddt_ticks,
            tMin=tmin,
            tMax=tmax,
            lint_bin_factor=lin_factor,
            logt_imax=log_bins,
        )
        bs = api.bootstrap_2d_fdc(
            sep, replicates, group_factor=group_factor, photon_factor=photon_factor, seed=seed
        )
        arrays = {f"total_{k}": v for k, v in sep.total().items()}
        arrays.update({f"mean_{k}": v for k, v in bs.mean.items()})
        arrays.update({f"std_{k}": v for k, v in bs.std.items()})
        np.savez_compressed(
            output,
            dT_ticks=sep.dT_ticks,
            lin_t=sep.lin_t,
            log_t=sep.log_t,
            photon_counts=sep.photon_counts,
            **arrays,
        )
        click.echo(f"Wrote {output} ({sep.n_molecules} molecules, {replicates} replicates)")
    except Exception as exc:  # noqa: BLE001
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


def _emit_json(payload: dict, output: str | None) -> None:
    """Print or write JSON payload."""
    text = json.dumps(payload, indent=2)
    if output:
        Path(output).write_text(text + "\n")
        click.echo(f"Wrote {output}")
    else:
        click.echo(text)


if __name__ == "__main__":
    cli()
