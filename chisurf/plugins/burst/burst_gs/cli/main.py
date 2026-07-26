"""Headless CLI for the Gopich-Szabo photon-by-photon kinetics fit."""

from __future__ import annotations

import json
import pathlib

import click
import numpy as np

from .. import core as _core


@click.command("burst-gs")
@click.argument("bur_files", type=click.Path(exists=True), nargs=-1)
@click.option("--data-dir", type=click.Path(exists=True), default=None,
              help="Folder the TTTR files named in the burst table resolve against "
                   "(defaults to the burst table's own folder).")
@click.option("--file-type", default="auto", help="TTTR container type, or 'auto'.")
@click.option("--donor", default="0,8", help="Routing channels counted as donor (colour 0).")
@click.option("--acceptor", default="1,9", help="Routing channels counted as acceptor (colour 1).")
@click.option("--tick", type=float, default=0.0,
              help="Macro-time tick in nanoseconds; 0 reads it from the file header. "
                   "Every fitted rate is proportional to this.")
@click.option("--min-photons", type=int, default=10, help="Smallest burst kept.")
@click.option("--max-bursts", type=int, default=0, help="Keep at most this many bursts (0 = all).")
@click.option("--states", type=int, default=2, help="Number of kinetic states.")
@click.option("--initial-rate", type=float, default=1000.0,
              help="Starting value for every rate, s^-1 (log-space optimisation, so the "
                   "order of magnitude is what matters).")
@click.option("--fix-efficiencies", is_flag=True,
              help="Fit only the rates, holding the efficiencies at their start values.")
@click.option("--efficiencies", default=None,
              help="Comma-separated starting (or fixed) per-state efficiencies.")
@click.option("--method", type=click.Choice(["nelder-mead", "l-bfgs-b"]),
              default="nelder-mead", help="Optimiser.")
@click.option("--max-iterations", type=int, default=2000, help="Optimiser iteration cap.")
@click.option("--scan-transition-time", is_flag=True,
              help="Also scan the log-likelihood against a finite transition duration.")
@click.option("--cross-check-h2mm", is_flag=True,
              help="Also fit the same photons with the discrete-time H2MM engine and compare.")
@click.option("--simulate", is_flag=True,
              help="Fit simulated two-state photons instead of files (no data needed).")
@click.option("--sim-rates", default="3000,1000", help="True k(1->2),k(2->1) of the simulation.")
@click.option("--sim-efficiencies", default="0.25,0.75", help="True per-state E of the simulation.")
@click.option("--sim-bursts", type=int, default=200, help="Simulated bursts.")
@click.option("--sim-photons", type=int, default=200, help="Photons per simulated burst.")
@click.option("--sim-rate-khz", type=float, default=50.0, help="Simulated photon rate in kHz.")
@click.option("--sim-seed", type=int, default=1, help="Simulation seed.")
@click.option("--as-json", is_flag=True, help="Print the whole result as JSON.")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Write the result as JSON to this file.")
def cli(bur_files, data_dir, file_type, donor, acceptor, tick, min_photons, max_bursts,
        states, initial_rate, fix_efficiencies, efficiencies, method, max_iterations,
        scan_transition_time, cross_check_h2mm, simulate, sim_rates, sim_efficiencies,
        sim_bursts, sim_photons, sim_rate_khz, sim_seed, as_json, output):
    """Fit continuous-time kinetics to the colours and arrival times of photons.

    Reads one or more ``.bur`` burst tables and their TTTR files, and fits rate
    constants and per-state FRET efficiencies by maximum likelihood without
    binning. With ``--simulate`` it needs no data at all, which is the quickest
    way to see what a given photon budget can resolve.
    """
    def numbers(text):
        return [float(v) for v in str(text).replace(";", ",").split(",") if v.strip()]

    def channels(text):
        return [int(v) for v in str(text).replace(";", ",").split(",") if v.strip()]

    if simulate:
        rates = numbers(sim_rates)
        eff = numbers(sim_efficiencies)
        bursts = _core.simulate_two_state(
            k_forward=rates[0], k_backward=rates[1], efficiencies=eff,
            photon_rate=sim_rate_khz * 1e3, n_bursts=sim_bursts,
            photons_per_burst=sim_photons, seed=sim_seed,
        )
        info = {
            "source": "simulation",
            "n_bursts": len(bursts),
            "n_photons": bursts.n_photons,
            "true_rates": rates,
            "true_efficiencies": eff,
        }
    else:
        if not bur_files:
            raise click.UsageError("give at least one .bur file, or use --simulate")
        folder = data_dir or str(pathlib.Path(bur_files[0]).parent)
        try:
            bursts, info = _core.load_photons(
                bur_files, folder,
                streams=[
                    {"name": "donor", "channels": channels(donor)},
                    {"name": "acceptor", "channels": channels(acceptor)},
                ],
                file_type=file_type,
                macro_time_resolution=(tick * 1e-9) if tick > 0 else None,
                min_photons=min_photons,
                max_bursts=max_bursts,
            )
        except Exception as exc:
            if as_json:
                click.echo(json.dumps({"error": str(exc)}))
            else:
                click.echo(f"Could not load the photons: {exc}", err=True)
            raise SystemExit(1) from exc

    start = np.array(numbers(efficiencies)) if efficiencies else None
    if start is not None and start.size != states:
        raise click.UsageError(f"--efficiencies needs {states} values for {states} states")

    analysis = _core.analyse(
        bursts,
        n_states=states,
        initial_rates=np.full(states * (states - 1), float(initial_rate)),
        initial_efficiencies=start,
        fix_efficiencies=fix_efficiencies,
        method=method,
        max_iterations=max_iterations,
        scan_transition_time=scan_transition_time,
        cross_check_h2mm=cross_check_h2mm,
        info=info,
    )

    payload = analysis.to_dict()
    if output:
        pathlib.Path(output).write_text(json.dumps(payload, indent=2) + "\n")
    if as_json:
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(analysis.report())
        if output:
            click.echo(f"\nWrote {output}")
    if not analysis.fit.success:
        raise SystemExit(2)


__all__ = ["cli"]
