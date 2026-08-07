"""Headless CLI: say what is in a ``.pto``, and how each result got there."""

from __future__ import annotations

import json

import click

from ..core import PtoInspection, settings_text


@click.group()
def cli():
    """Inspect a photon container without opening a window.

    A ``.pto`` is one measurement: the instrument file verbatim, and every result
    computed from it beside it, each recording the operation and the settings
    that produced it. ``list`` shows the objects, ``show`` describes one,
    ``lineage`` walks a result back to the primary data, and ``verify`` checks
    every checksum.
    """


@cli.command("list")
@click.argument("path", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="Emit the records as JSON.")
def list_objects(path: str, as_json: bool) -> None:
    """List every object in the container."""
    with PtoInspection(path) as insp:
        rows = insp.rows()
        if as_json:
            click.echo(json.dumps(rows, indent=2))
            return
        click.echo(
            f"{'uid':>8}  {'name':<24} {'kind':<20} {'operation':<24} "
            f"{'grain':<12} {'rows':>9}  size"
        )
        for row in rows:
            click.echo(
                f"{row['uid_short']:>8}  {row['name'][:24]:<24} {row['kind'][:20]:<20} "
                f"{(row['operation'] or '—')[:24]:<24} {(row['grain'] or '—')[:12]:<12} "
                f"{row['rows'] or '—':>9}  {row['size']}"
            )


@cli.command("show")
@click.argument("path", type=click.Path(exists=True))
@click.argument("ref")
def show(path: str, ref: str) -> None:
    """Describe one object, by name or UID."""
    with PtoInspection(path) as insp:
        uid = _resolve(insp, ref)
        item = insp.info(uid)
        if item is None:
            raise click.ClickException(f"no object {ref!r}")
        click.echo(f"{item.name}  [{item.kind}]")
        click.echo(f"  uid        {item.uid}")
        click.echo(f"  operation  {item.operation or '—'}")
        click.echo(f"  grain      {item.grain or '—'}")
        click.echo(f"  rows       {item.rows if item.is_tabular else '—'}")
        click.echo(f"  size       {item.size_bytes:,} B")
        click.echo(f"  software   {item.software or '—'}")
        click.echo(f"  run id     {item.settings_hash or '—'}")
        text = settings_text(item.settings)
        if text:
            click.echo("  settings")
            for line in text.splitlines():
                click.echo(f"    {line}")


@cli.command("lineage")
@click.argument("path", type=click.Path(exists=True))
@click.argument("ref")
def lineage(path: str, ref: str) -> None:
    """Walk an object back to the primary data, with every setting in between."""
    with PtoInspection(path) as insp:
        click.echo(insp.describe_lineage(_resolve(insp, ref)))


@cli.command("graph")
@click.argument("path", type=click.Path(exists=True))
@click.option("--out", type=click.Path(), default="", help="Write the graph JSON here.")
def graph(path: str, out: str) -> None:
    """Emit the provenance DAG in the node-editor graph format."""
    with PtoInspection(path) as insp:
        text = json.dumps(insp.graph(), indent=2)
    if out:
        with open(out, "w", encoding="utf-8") as handle:
            handle.write(text)
        click.echo(f"wrote {out}")
    else:
        click.echo(text)


@cli.command("verify")
@click.argument("path", type=click.Path(exists=True))
def verify(path: str) -> None:
    """Check every recorded checksum against the stored bytes."""
    with PtoInspection(path) as insp:
        problems = insp.verify()
    if not problems:
        click.echo("every recorded checksum matches")
        return
    for problem in problems:
        click.echo(problem)
    raise SystemExit(1)


@cli.command("export")
@click.argument("path", type=click.Path(exists=True))
@click.argument("ref")
@click.argument("out", type=click.Path())
@click.option("--delimiter", default=",", show_default=True)
def export(path: str, ref: str, out: str, delimiter: str) -> None:
    """Write one tabular payload out as delimited text."""
    from chisurf.core.datastore import write_csv_table

    with PtoInspection(path) as insp:
        store = insp.store(_resolve(insp, ref))
        if store is None:
            raise click.ClickException(f"{ref!r} is not a table")
        write_csv_table(out, store, delimiter=delimiter)
    click.echo(f"wrote {out}")


def _resolve(insp: PtoInspection, ref: str) -> int:
    """Return the UID for a name or a (possibly abbreviated) UID."""
    for item in insp.infos():
        if item.name == ref or str(item.uid) == ref:
            return item.uid
    raise click.ClickException(f"no object {ref!r}")


if __name__ == "__main__":
    cli()
