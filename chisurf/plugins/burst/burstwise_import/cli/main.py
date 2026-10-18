"""CLI entrypoint for the burstwise_import plugin."""

from __future__ import annotations

import click

from chisurf.plugins.burst.burstwise_import.api import ImportSettings, import_folder


@click.group(name="burstwise-import")
def cli():
    """Convert legacy burstwise analysis folders to PTO.MFDB containers."""


@cli.command()
@click.argument("folder", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--source-mode",
    type=click.Choice(["beside", "mti_prefix", "none"]),
    default="beside",
    help="How the raw TTTR per stem is found.",
)
@click.option(
    "--prefix",
    "prefixes",
    multiple=True,
    nargs=2,
    help="OLD NEW path-prefix pair for source-mode mti_prefix (repeatable).",
)
@click.option("--out-dir", "-o", type=click.Path(file_okay=False), default=None)
@click.option("--dry-run", is_flag=True, help="Report only; write nothing.")
@click.option(
    "--raw-data",
    type=click.Choice(["embed", "sidecar"]),
    default="sidecar",
    help="sidecar: analysis-only container, raw file stays beside it (deposition default).",
)
def convert(
    folder: str,
    source_mode: str,
    prefixes: tuple,
    out_dir: str | None,
    dry_run: bool,
    raw_data: str,
):
    """Convert FOLDER (a burstwise_* analysis tree) to .mmfdb.pto containers."""
    settings = ImportSettings(
        out_dir=out_dir,
        dry_run=dry_run,
        source_mode=source_mode,
        raw_data=raw_data,
        mti_prefix_map={old: new for old, new in prefixes},
    )
    report = import_folder(folder, settings)
    click.echo(report.summary())
    if report.unmapped_columns:
        click.echo("unmapped columns (kept verbatim):")
        for stem, cols in report.unmapped_columns.items():
            for c in cols:
                click.echo(f"  {stem}: {c}")


@cli.command()
@click.argument("folder", type=click.Path(exists=True, file_okay=False))
def scan(folder: str):
    """Inventory FOLDER: stems, tables, Info file, mti map."""
    from chisurf.core.fio.fluorescence.burstwise_import import scan_folder

    inv = scan_folder(folder)
    click.echo(f"stems: {len(inv['tables'])}")
    click.echo(f"info: {inv['info']}")
    click.echo(f"mti: {inv['mti']}")
    if inv["parameters"]:
        click.echo(f"parameters: {inv['parameters']}")
    for stem, roles in sorted(inv["tables"].items())[:5]:
        click.echo(f"  {stem}: {sorted(roles)}")
    if len(inv["tables"]) > 5:
        click.echo(f"  ... and {len(inv['tables']) - 5} more")
