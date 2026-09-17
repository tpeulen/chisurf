"""Headless CLI for the accurate-FRET calibration."""

from __future__ import annotations

import json

import click
import numpy as np

from .. import core as _core


@click.command("accurate-fret")
@click.argument("burst_table", type=click.Path(exists=True), required=False)
@click.option(
    "--i-dd",
    "column_i_dd",
    default=None,
    help="Column of the donor signal under donor excitation (auto-detected).",
)
@click.option(
    "--i-da",
    "column_i_da",
    default=None,
    help="Column of the acceptor signal under donor excitation (auto-detected).",
)
@click.option(
    "--i-aa",
    "column_i_aa",
    default=None,
    help="Column of the acceptor signal under acceptor excitation (auto-detected).",
)
@click.option(
    "--tau",
    "column_tau",
    default=None,
    help="Column of the per-burst donor lifetime in ns (auto-detected).",
)
@click.option("--tau-d0", type=float, default=4.0, help="Donor-only lifetime tau_D(0) in ns.")
@click.option("--r0", type=float, default=52.0, help="Förster radius in Angstrom.")
@click.option(
    "--linker-sigma",
    type=float,
    default=6.0,
    help="Width of the linker distance distribution (Angstrom).",
)
@click.option(
    "--background",
    nargs=3,
    type=float,
    default=(0.0, 0.0, 0.0),
    help="Backgrounds Bg_DD Bg_DA Bg_AA in the units of the columns.",
)
@click.option(
    "--gamma-source",
    type=click.Choice(["auto", "es", "lifetime", "combined"]),
    default="auto",
    help="Route that determines gamma.",
)
@click.option(
    "--lightpath", default=None, help="Operation id of a saved light path used as the optics prior."
)
@click.option("--no-priors", is_flag=True, help="Ignore the optics priors (data only).")
@click.option("--bootstrap", type=int, default=50, help="Bootstrap resamples (0 disables).")
@click.option(
    "--max-populations",
    type=int,
    default=3,
    help="Largest number of FRET sub-populations searched.",
)
@click.option(
    "--list-lightpaths",
    is_flag=True,
    help="List the saved light paths that can serve as the prior, then exit.",
)
@click.option("--list-columns", is_flag=True, help="List the table's columns, then exit.")
@click.option("--as-json", is_flag=True, help="Print the calibration as JSON.")
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Write the per-burst accurate values to this CSV file.",
)
@click.option(
    "--simulate",
    type=click.Path(),
    default=None,
    help="Simulate an ALEX measurement with known factors, write its burst "
    "table here and calibrate that instead of a file.",
)
@click.option(
    "--simulate-photons", type=int, default=350_000, help="Photon budget of the simulation."
)
@click.option("--simulate-seed", type=int, default=3, help="Seed of the simulation.")
def cli(
    burst_table,
    column_i_dd,
    column_i_da,
    column_i_aa,
    column_tau,
    tau_d0,
    r0,
    linker_sigma,
    background,
    gamma_source,
    lightpath,
    no_priors,
    bootstrap,
    max_populations,
    list_lightpaths,
    list_columns,
    as_json,
    output,
    simulate,
    simulate_photons,
    simulate_seed,
):
    """Calibrate accurate FRET from a per-burst table.

    Finds the donor-only, acceptor-only and FRET populations automatically,
    determines alpha, beta, gamma and delta from them (combined with the optics
    prior of a saved light path), and reports the accurate efficiency and
    distance of every population.
    """
    if list_lightpaths:
        for entry in _core.list_lightpaths():
            click.echo(f"{entry['operation_id']}\t{entry.get('name', '')}")
        return

    if simulate:
        burst_table = _write_simulated_table(
            simulate, simulate_photons, simulate_seed, tau_d0, r0, linker_sigma
        )
        click.echo(f"simulated burst table: {burst_table}")
    if not burst_table:
        raise click.UsageError("give a burst table, or --simulate a measurement")

    columns = _core.read_burst_table(burst_table)
    if list_columns:
        for name in columns:
            click.echo(name)
        return

    guess = _core.guess_columns(columns)
    mapping = {
        "i_dd": column_i_dd or guess.get("i_dd"),
        "i_da": column_i_da or guess.get("i_da"),
        "i_aa": column_i_aa or guess.get("i_aa"),
        "tau_f": column_tau or guess.get("tau_f"),
    }
    for role in ("i_dd", "i_da"):
        if not mapping[role] or mapping[role] not in columns:
            raise click.ClickException(
                f"column for {role} not found; pass --{role.replace('_', '-')} "
                f"(available: {', '.join(columns)})"
            )

    def _column(role):
        name = mapping[role]
        return None if not name or name not in columns else np.asarray(columns[name], float)

    prior = None
    if lightpath:
        prior = _core.lightpath_prior(lightpath)

    result = _core.calibrate(
        _column("i_dd"),
        _column("i_da"),
        _column("i_aa"),
        _column("tau_f"),
        donor_lifetime=tau_d0,
        forster_radius=r0,
        linker_sigma=linker_sigma,
        background=background,
        gamma_source=gamma_source,
        n_bootstrap=bootstrap,
        lightpath=prior,
        use_priors=not no_priors,
        max_fret_populations=max_populations,
    )

    if as_json:
        click.echo(
            json.dumps(
                {
                    "factors": result.factors,
                    "uncertainties": result.calibration.uncertainties,
                    "gamma_estimates": result.calibration.gamma_estimates,
                    "populations": result.calibration.populations,
                    "messages": result.calibration.messages,
                    "converged": result.calibration.converged,
                },
                indent=2,
                default=float,
            )
        )
    else:
        click.echo(result.calibration.report())

    if output:
        _core.export_csv(output, result)
        click.echo(f"wrote {output}")


def _write_simulated_table(path, n_photons, seed, tau_d0, r0, linker_sigma):
    """Simulate an ALEX measurement with known factors and write its burst table.

    Lets the tool be tried — and its recovery checked — without any data: the
    factors that produced the file are written into its header.

    Parameters
    ----------
    path : str
        Destination CSV file.
    n_photons : int
        Photon budget of the simulation.
    seed : int
        Random seed.
    tau_d0, r0, linker_sigma : float
        Donor lifetime (ns), Förster radius (Å) and linker width (Å) to simulate.

    Returns
    -------
    str
        The path that was written.
    """
    import numpy as np

    from chisurf.core.fluorescence.burst.simulate import SmfretParameters, simulate_smfret

    parameters = SmfretParameters(
        n_photons=int(n_photons),
        seed=int(seed),
        tau_d0=float(tau_d0),
        r0=float(r0),
        linker_sigma=float(linker_sigma),
        alex_period=0.1,
    )
    simulation = simulate_smfret(parameters)
    bursts = simulation.burst_table(min_photons=50)
    header = [
        "# simulated ALEX measurement (tttrlib) — the declared truth:",
        f"#   gamma={parameters.gamma} alpha={parameters.alpha} "
        f"beta={parameters.beta} delta={parameters.delta}",
        f"#   E={parameters.efficiencies} tau_D0={parameters.tau_d0} "
        f"R0={parameters.r0} linker_sigma={parameters.linker_sigma}",
        "i_dd,i_da,i_aa,tau_f,n_photons,species",
    ]
    data = np.column_stack(
        [bursts[k] for k in ("i_dd", "i_da", "i_aa", "tau_f", "n_photons", "species")]
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(header) + "\n")
        np.savetxt(fh, data, delimiter=",", fmt="%.6g")
    return str(path)


if __name__ == "__main__":  # pragma: no cover
    cli()
