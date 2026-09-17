"""Headless CLI for the MFD preparation plugin (see /plugins/burst.md).

Usage::

    csc mfd-prepare prepare /path/to/burst_folder
    csc mfd-prepare prepare /path/to/burst_folder --no-photons
    csc mfd-prepare fit /path/to/burst_folder --n-states 2
    csc mfd-prepare contract
"""

from __future__ import annotations

import json
import sys

import click

from ..api import describe_preparation, prepare_folder
from ..api.models import PrepareRequest


@click.group()
@click.version_option()
def cli():
    """Prepare burst folders for multiparameter-fluorescence analysis."""


@cli.command()
@click.argument("folder", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--no-photons",
    is_flag=True,
    default=False,
    help="Skip loading photons (faster; no micro-time/agreement check).",
)
@click.option(
    "--report-only",
    is_flag=True,
    default=False,
    help="Print only the human-readable report, not the JSON result.",
)
def prepare(folder: str, no_photons: bool, report_only: bool):
    """Prepare FOLDER for MFD analysis and print the result."""
    request = PrepareRequest(
        folder=folder,
        with_photons=not no_photons,
    )
    result = prepare_folder(request)
    if result.error:
        click.echo(f"Error: {result.error}", err=True)
        sys.exit(1)
    if report_only:
        click.echo(result.report)
    else:
        click.echo(json.dumps(result.to_dict(), indent=2, default=str))


@cli.command()
@click.argument("folder", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--n-states",
    default=2,
    show_default=True,
    type=int,
    help="Number of species/states in the kinetic model.",
)
@click.option(
    "--green",
    default="green",
    show_default=True,
    help="Green detector channel name.",
)
@click.option(
    "--red",
    default="red",
    show_default=True,
    help="Red detector channel name.",
)
@click.option(
    "--n-ratio-bins",
    default=41,
    show_default=True,
    type=int,
    help="Number of bins on the FRET-ratio (S) axis.",
)
@click.option(
    "--n-micro-time-bins",
    default=41,
    show_default=True,
    type=int,
    help="Number of bins on the micro-time axis.",
)
@click.option(
    "--min-green-photons",
    default=20,
    show_default=True,
    type=int,
    help="Minimum green photons per burst.",
)
def fit(
    folder: str,
    n_states: int,
    green: str,
    red: str,
    n_ratio_bins: int,
    n_micro_time_bins: int,
    min_green_photons: int,
):
    """Fit an MFD kinetic model to FOLDER and print the fitted parameters."""
    try:
        from chisurf.core.experiments.mfd.reader import MfdReader
        from chisurf.core.fitting.fit import Fit
        from chisurf.core.models.mfd.two_dimensional import Mfd2DModel

        reader = MfdReader(
            green=green,
            red=red,
            n_ratio_bins=n_ratio_bins,
            n_micro_time_bins=n_micro_time_bins,
            min_green_photons=min_green_photons,
        )
        reader.read(folder)
        data = reader.data

        fit = Fit(
            model_class=Mfd2DModel,
            data=data,
            model_kw={"n_states": n_states},
        )
        fit.run()

        params = dict(
            zip(
                fit.model.parameter_names,
                fit.model.parameter_values,
            )
        )
        uncertainties = dict(
            zip(
                fit.model.parameter_names,
                fit.model.parameter_uncertainties,
            )
        )
        result = {
            "n_states": n_states,
            "parameters": params,
            "uncertainties": uncertainties,
            "summary": fit.model.summary_text(),
        }
        click.echo(json.dumps(result, indent=2, default=str))
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.command()
def contract():
    """Print the plugin's RPC contract descriptor."""
    click.echo(json.dumps(describe_preparation(), indent=2))


if __name__ == "__main__":
    cli()
