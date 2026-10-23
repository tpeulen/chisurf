"""``csc legacy-export`` -- the headless twin of the legacy-export window."""

from __future__ import annotations

import pathlib

import click


@click.group("legacy-export")
def cli() -> None:
    """Unpack .pto containers into the legacy formats (burst folder, ALEX CSVs)."""


@cli.command("burst-folder")
@click.argument("container", type=click.Path(exists=True))
@click.argument("out_dir", type=click.Path(), required=False)
def burst_folder(container: str, out_dir: str | None) -> None:
    """Write the Seidel/Margarita burst folder: bi4_bur/*.bur plus companions.

    OUT_DIR defaults to beside CONTAINER.
    """
    from chisurf.plugins.core.legacy_export import core

    for path in core.export_burst_folder(container, out_dir):
        click.echo(f"wrote       {path}")


@cli.command("alex-csvs")
@click.argument("burst_table", type=click.Path(exists=True))
@click.argument("stem", type=click.Path())
@click.option("--sample", default="", help="Sample description written into the _meta file.")
@click.option("--buffer", "buffer_", default="", help="Buffer description written into the _meta file.")
@click.option(
    "--parts",
    default="meta,hist_E,hist_S,hist_2D",
    show_default=True,
    help="Comma-separated subset of meta,hist_E,hist_S,hist_2D,original_bursts.",
)
def alex_csvs(burst_table: str, stem: str, sample: str, buffer_: str, parts: str) -> None:
    """Write the five ALEX-Suite CSV files beside STEM.

    BURST_TABLE is a .bur table or a .pto run (``m000.pto/<run>``).
    """
    from chisurf.plugins.core.legacy_export import core

    requested = tuple(part.strip() for part in parts.split(",") if part.strip())
    allowed = ("meta", "hist_E", "hist_S", "hist_2D", "original_bursts")
    unknown = [part for part in requested if part not in allowed]
    if unknown:
        raise click.ClickException(f"unknown part(s) {unknown}; the parts are {allowed}")
    for path in core.export_alex_csvs(
        burst_table, stem, sample=sample, buffer=buffer_, parts=requested
    ):
        click.echo(f"wrote       {path}")


@cli.command("plan")
@click.argument("container", type=click.Path(exists=True))
def plan(container: str) -> None:
    """List what the burst-folder export would write for each run of CONTAINER."""
    from chisurf.plugins.core.legacy_export import core

    rows = core.export_plan(container)
    if not rows:
        click.echo("no analysis runs")
        return
    for row in rows:
        click.echo(
            f"{row['run']:40s} {row['operation']:28s} -> {row['ending'] or '(skipped)'}"
        )
