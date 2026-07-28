"""CLI entrypoint for hidden-Markov-model analysis of binned traces.

Reads a trace from a text or ``.npy`` file (rows = time bins, columns =
channels) and writes the fit as JSON, so the analysis is scriptable without a
display::

    csg-hmm fit trace.csv --states 3 --time-step 0.001 -o fit.json
    csg-hmm scan trace.csv --min-states 1 --max-states 6
"""

from __future__ import annotations

import json
import pathlib

import click
import numpy as np

from ..api.models import HmmSettings
from ..core.analysis import fit_traces, scan_state_counts

__all__ = ["cli", "load_trace"]


def load_trace(path: str) -> np.ndarray:
    """Load a binned trace from ``.npy`` or a delimited text file.

    Parameters
    ----------
    path : str
        File to read. ``.npy`` is loaded as-is; anything else is parsed as
        delimited text, comma-separated if the first non-comment line contains
        a comma.

    Returns
    -------
    numpy.ndarray
        Trace of shape ``(n_bins, n_channels)``.
    """
    file = pathlib.Path(path)
    if file.suffix.lower() == ".npy":
        data = np.load(file)
    else:
        text = file.read_text().splitlines()
        sample = next((line for line in text if line and not line.startswith("#")), "")
        data = np.loadtxt(file, delimiter="," if "," in sample else None)
    return data if data.ndim == 2 else data[:, None]


def _settings(states, covariance, iterations, tol, time_step, seed, no_accelerate):
    """Build :class:`HmmSettings` from the shared command-line options."""
    return HmmSettings(
        n_states=states,
        covariance_type=covariance,
        n_iter=iterations,
        tol=tol,
        time_step=time_step,
        random_state=seed,
        accelerate=not no_accelerate,
    )


_COMMON = [
    click.option("--covariance", default="full",
                 type=click.Choice(["spherical", "diag", "full", "tied"]),
                 help="Emission covariance parameterisation"),
    click.option("--iterations", default=1000, type=int, help="Maximum EM maps"),
    click.option("--tol", default=1e-2, type=float, help="Log-likelihood convergence threshold"),
    click.option("--time-step", default=1.0, type=float,
                 help="Duration of one bin in seconds (dwell times use it)"),
    click.option("--seed", default=0, type=int, help="Initialisation seed"),
    click.option("--no-accelerate", is_flag=True, help="Plain Baum-Welch, without SQUAREM"),
    click.option("--output", "-o", type=click.Path(), help="Write the JSON result here"),
]


def _add_options(command):
    """Apply the shared options to a command (decorators apply bottom-up)."""
    for option in reversed(_COMMON):
        command = option(command)
    return command


def _emit(payload: dict, output: str | None) -> None:
    """Write ``payload`` as JSON to ``output`` or to stdout."""
    text = json.dumps(payload, indent=2)
    if output:
        pathlib.Path(output).write_text(text)
        click.echo(f"wrote {output}")
    else:
        click.echo(text)


@click.group(name="hmm")
def cli():
    """Gaussian hidden Markov models for binned time traces."""


@cli.command()
@click.argument("trace_file", type=click.Path(exists=True))
@click.option("--states", default=2, type=int, help="Number of states to fit")
@_add_options
def fit(trace_file, states, covariance, iterations, tol, time_step, seed, no_accelerate, output):
    """Fit an HMM to TRACE_FILE and report states, dwells and transitions."""
    result = fit_traces(
        load_trace(trace_file),
        _settings(states, covariance, iterations, tol, time_step, seed, no_accelerate),
    )
    payload = result.to_dict()
    if not output:
        # The full state path is one entry per bin; a summary is what a person
        # reads on a terminal, and -o still writes everything.
        payload.pop("states")
        payload.pop("dwell_times")
    _emit(payload, output)


@cli.command()
@click.argument("trace_file", type=click.Path(exists=True))
@click.option("--min-states", default=1, type=int, help="Smallest state count to try")
@click.option("--max-states", default=6, type=int, help="Largest state count to try")
@_add_options
def scan(trace_file, min_states, max_states, covariance, iterations, tol, time_step, seed,
         no_accelerate, output):
    """Score state counts on TRACE_FILE by AIC and BIC."""
    result = scan_state_counts(
        load_trace(trace_file),
        _settings(min_states, covariance, iterations, tol, time_step, seed, no_accelerate),
        min_states=min_states,
        max_states=max_states,
    )
    _emit(result.to_dict(), output)


if __name__ == "__main__":
    cli()
