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


@cli.command("ask")
@click.argument("question", nargs=-1, required=True)
@click.option("--model", default="", help="Model identifier override.")
@click.option("--provider", default="", help="Provider key override.")
@click.option("--json", "as_json", is_flag=True, help="Print the answer as JSON.")
def ask_docs(question: tuple, model: str, provider: str, as_json: bool):
    r"""Ask ChiSurf's documentation a question and get a cited answer.

    The assistant may only browse, search and read documentation — it cannot
    load data, fit, or run code. A language-model provider must be configured
    in Settings → AI (or through the usual API-key environment variables).

    \b
    csc help ask "what does the gamma factor correct for?"
    csc help ask "how do I fuse bursts?" --json
    """
    from chisurf.plugins.core.help.api import ask as ask_api

    answer = ask_api.ask(" ".join(question), model=model, provider=provider)

    if as_json:
        import json as _json

        click.echo(_json.dumps(answer.to_dict(), indent=2))
        raise SystemExit(0 if answer.ok else 1)

    if answer.error and not answer.text:
        click.echo(f"Error: {answer.error}", err=True)
        raise SystemExit(1)
    click.echo(answer.text)
    if answer.pages:
        click.echo("")
        click.echo("Sources:")
        for page in answer.pages:
            title = page["title"] or page["document"]
            click.echo(f"  {title} — {page['document']}")
    else:
        click.echo("")
        click.echo(
            "No documentation page was opened for this answer — treat it as a "
            "suggestion and check it.",
            err=True,
        )
    if answer.fabricated:
        click.echo(
            "It also named pages that do not exist: "
            + ", ".join(answer.fabricated),
            err=True,
        )
    if not answer.ok:
        raise SystemExit(1)


@cli.command("review-check")
@click.option(
    "--quiet", is_flag=True, help="Print only the summary line, not each page."
)
def review_check(quiet: bool):
    """Fail if any review-tracked page is unreviewed or stale.

    This is the release gate: exit code 1 means human-unchecked documentation
    would ship. An *ai-reviewed* page has been read and corrected by an agent
    but still counts as blocking — an agent cannot check a screenshot against
    the running interface. Pages become *stale* when edited after sign-off.
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
        click.echo(
            "An agent that has read and corrected a page records that with:",
            err=True,
        )
        click.echo("  csc help review-set <path> --ai", err=True)
    raise SystemExit(1)


@cli.command("review-list")
@click.option(
    "--status",
    type=click.Choice(["reviewed", "ai-reviewed", "stale", "unreviewed", "all"]),
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
        click.echo(f"  [{page.status:<11}] {page.rel_path}{who}")
    click.echo("")
    click.echo(report.summary())


@cli.command("review-set")
@click.argument("path", type=str, nargs=-1, required=True)
@click.option("--reviewer", default="", help="Name to record with the sign-off.")
@click.option(
    "--ai",
    is_flag=True,
    help=(
        "Record an agent's review instead of a human's. Weaker: it says the "
        "page was read and corrected, not that it was checked against the "
        "running application, and it does not clear the release gate."
    ),
)
@click.option(
    "--unreview", is_flag=True, help="Clear the sign-off instead of granting it."
)
def review_set(path: tuple, reviewer: str, ai: bool, unreview: bool):
    """Record that PATH has been reviewed (or clear that record).

    Several paths may be given, which is how an agent records a pass over a
    whole directory. A human sign-off is never overwritten by ``--ai``.
    """
    from chisurf.plugins.core.help.api import review

    if unreview:
        target = review.STATUS_UNREVIEWED
    elif ai:
        target = review.STATUS_AI_REVIEWED
    else:
        target = review.STATUS_REVIEWED
    if ai and not reviewer:
        reviewer = "agent"

    failed = False
    for one in path:
        if not review.is_tracked(one):
            click.echo(f"Error: {one} is not review-tracked", err=True)
            failed = True
            continue
        if not review.set_status(one, target, reviewer):
            click.echo(f"Error: cannot record status for {one}", err=True)
            failed = True
            continue
        click.echo(f"{review.status_of(one).status}: {one}")
    if failed:
        raise SystemExit(1)
