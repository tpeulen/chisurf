"""CLI commands for the Help plugin."""

from __future__ import annotations

import click


@click.group(name="help")
def cli():
    """Browse ChiSurf documentation from the command line."""


@cli.command("list")
def list_docs():
    """List all available documentation files."""
    from chisurf.plugins.core.help.api.io import discover_docs

    info = discover_docs()
    click.echo(f"Found {len(info.entries)} documentation files:")
    click.echo("")
    for entry in info.entries:
        click.echo(f"  [{entry.category}] {entry.title}")
        click.echo(f"         {entry.path}")


@cli.command("read")
@click.argument("path", type=str)
def read_doc(path: str):
    """Read a documentation file and print its Markdown content."""
    from chisurf.plugins.core.help.api.io import read_doc

    content = read_doc(path)
    if content is None:
        click.echo(f"Error: cannot read {path}", err=True)
        raise SystemExit(1)
    click.echo(content)


@cli.command("render")
@click.argument("path", type=str)
def render_doc(path: str):
    """Render a documentation file to HTML and print.

    Handles both Markdown and the reStructuredText user manual.
    """
    from chisurf.plugins.core.help.api.io import read_doc
    from chisurf.plugins.core.help.api.render import render_document

    content = read_doc(path)
    if content is None:
        click.echo(f"Error: cannot read {path}", err=True)
        raise SystemExit(1)
    html = render_document(content, path)
    if html is None:
        click.echo(f"Error: no renderer available for {path}", err=True)
        raise SystemExit(1)
    click.echo(html)


@cli.command("review-check")
@click.option(
    "--quiet", is_flag=True, help="Print only the summary line, not each page."
)
def review_check(quiet: bool):
    """Fail if any review-tracked page is unreviewed or stale.

    This is the release gate: exit code 1 means human-unchecked documentation
    would ship. Pages become *stale* when edited after sign-off.
    """
    from chisurf.plugins.core.help.api import review

    report = review.scan()
    if report.ok:
        click.echo(f"All documentation reviewed - {report.summary()}")
        return

    click.echo(f"Unreviewed documentation - {report.summary()}", err=True)
    if not quiet:
        click.echo("", err=True)
        for page in sorted(report.blocking, key=lambda p: (p.status, p.rel_path)):
            click.echo(f"  [{page.status:<10}] {page.rel_path}", err=True)
        click.echo("", err=True)
        click.echo(
            "Review pages in the Help browser (Help:Documentation), or run:",
            err=True,
        )
        click.echo("  csc help review-set <path> --reviewer <name>", err=True)
    raise SystemExit(1)


@cli.command("review-list")
@click.option(
    "--status",
    type=click.Choice(["reviewed", "stale", "unreviewed", "all"]),
    default="all",
    help="Only show pages with this status.",
)
def review_list(status: str):
    """List review-tracked pages and their sign-off status."""
    from chisurf.plugins.core.help.api import review

    report = review.scan()
    pages = report.pages if status == "all" else [
        p for p in report.pages if p.status == status
    ]
    if not pages:
        click.echo("No matching pages.")
        return
    for page in sorted(pages, key=lambda p: p.rel_path):
        who = f"  ({page.reviewer} {page.date})" if page.reviewer else ""
        click.echo(f"  [{page.status:<10}] {page.rel_path}{who}")
    click.echo("")
    click.echo(report.summary())


@cli.command("review-set")
@click.argument("path", type=str)
@click.option("--reviewer", default="", help="Name to record with the sign-off.")
@click.option(
    "--unreview", is_flag=True, help="Clear the sign-off instead of granting it."
)
def review_set(path: str, reviewer: str, unreview: bool):
    """Record that a human has checked PATH (or clear that record)."""
    from chisurf.plugins.core.help.api import review

    if not review.is_tracked(path):
        click.echo(f"Error: {path} is not review-tracked", err=True)
        raise SystemExit(1)
    target = review.STATUS_UNREVIEWED if unreview else review.STATUS_REVIEWED
    if not review.set_status(path, target, reviewer):
        click.echo(f"Error: cannot record status for {path}", err=True)
        raise SystemExit(1)
    click.echo(f"{review.status_of(path).status}: {path}")


@cli.command("search")
@click.argument("query", type=str)
def search(query: str):
    """Search documentation files for a query string."""
    from chisurf.plugins.core.help.api.io import search_docs

    results = search_docs(query)
    if not results:
        click.echo("No results found.")
        return
    click.echo(f"Found {len(results)} result(s):")
    click.echo("")
    for r in results:
        click.echo(f"  [{r['match_type']}] {r['title']}")
        click.echo(f"         {r['path']}")


if __name__ == "__main__":
    cli()

