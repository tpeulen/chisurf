"""CLI entrypoint for ebFRET binned-trace HMM analysis."""

from __future__ import annotations

import json

import click

from chisurf.plugins.burst.burst_ebfret.api.models import EbfretSettings
from chisurf.plugins.burst.burst_ebfret.backend.services import (
    _analysis_to_jsonable,
    run_analysis,
)
from chisurf.plugins.burst.burst_ebfret.io import load_stacked_dat


@click.group(name="ebfret")
def cli():
    """Empirical-Bayes Gaussian HMM for binned single-molecule FRET traces."""


@cli.command()
@click.argument("dat_file", type=click.Path(exists=True))
@click.option("--min-states", default=2, type=int, help="Smallest state count to scan")
@click.option("--max-states", default=4, type=int, help="Largest state count to scan")
@click.option("--max-iter", default=20, type=int, help="Max empirical-Bayes iterations")
@click.option("--vbem-max-iter", default=100, type=int, help="Max per-trace VBEM iterations")
@click.option("--limit", default=0, type=int, help="Fit only the first N traces (0 = all)")
@click.option("--seed", default=0, type=int, help="Prior-initialisation seed")
@click.option("--output", "-o", type=click.Path(), help="Write the JSON summary to this path")
@click.option("--container", is_flag=True,
              help="Also write the result into <dat_file>.pto, beside the traces")
def compute(dat_file, min_states, max_states, max_iter, vbem_max_iter, limit, seed,
            output, container):
    """Fit an ebFRET model to a stacked ``[id, donor, acceptor]`` ``.dat`` file."""
    traces = load_stacked_dat(dat_file)
    if limit > 0:
        traces = traces[:limit]
    settings = EbfretSettings(
        min_states=min_states,
        max_states=max_states,
        max_iter=max_iter,
        vbem_max_iter=vbem_max_iter,
        seed=seed,
    )
    analysis = run_analysis(traces, settings)
    summary = _analysis_to_jsonable(analysis)
    text = json.dumps(summary, indent=2)
    if output:
        with open(output, "w") as handle:
            handle.write(text)
    if container:
        from chisurf.plugins.burst.burst_ebfret.core.analysis import write_container

        path = write_container(
            dat_file, analysis,
            parameters={
                "min_states": min_states, "max_states": max_states,
                "max_iter": max_iter, "vbem_max_iter": vbem_max_iter,
                "limit": limit, "seed": seed,
            },
        )
        click.echo(f"container: {path}")
    means = ", ".join(f"{s.mean:.3f}" for s in analysis.states)
    click.echo(f"selected K={analysis.n_states}  state means: [{means}]")
    click.echo(f"evidence={analysis.evidence:.1f}  dwells={len(analysis.dwells)}")
    if not output:
        click.echo(text)


if __name__ == "__main__":
    cli()
