"""``csc windows`` -- detect excitation windows and check a setup's windows, headless.

Examples::

    csc windows detect run.ptu
    csc windows detect run.ptu --json
    csc windows check run.ptu --setup mt200.setup.json
    csc windows check run.ptu --setup mt200.setup.json --write fixed.setup.json

``check`` exits 0 when the windows match (or the data is donor-only / not PIE), 1 when they do
not (a warning or an error), so a script can stop before a burst analysis.
"""

from __future__ import annotations

import json
import sys

import click

from .. import api


def _windows_lines(det: dict) -> list[str]:
    ns = det.get("windows_ns") or {}
    unit = "ticks" if det.get("domain") == "macro" else "ch"
    return [
        f"  {name:10s} {lo:6d}–{hi:<6d} {unit}   {ns[name][0]:8.2f}–{ns[name][1]:.2f} ns"
        for name, (lo, hi) in (det.get("windows") or {}).items()
    ]


@click.group(context_settings={"help_option_names": ["-h", "--help"]}, invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Excitation windows: detect PIE pulses / µs-ALEX alternation, check a setup's windows."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.argument("measurement")
@click.option("--setup", default=None, help="Setup JSON (its detectors name the histograms).")
@click.option(
    "--kind", type=click.Choice(["auto", "pie", "alex"]), default="auto", show_default=True,
    help="auto: PIE in the micro time, else µs-ALEX in the macro time.",
)
@click.option("--json", "as_json", is_flag=True, help="Print the full result as JSON.")
def detect(measurement, setup, kind, as_json):
    """Detect the excitation scheme of MEASUREMENT and propose windows."""
    det = api.detect(measurement, setup, kind)
    if as_json:
        click.echo(json.dumps(det, indent=2))
        return
    click.echo(f"{det['kind']}: {det['message']}")
    for line in _windows_lines(det):
        click.echo(line)
    for note in det.get("notes") or []:
        click.echo(f"  note: {note}")


@cli.command()
@click.argument("measurement")
@click.option("--setup", required=True, help="Setup JSON whose windows are checked.")
@click.option("--json", "as_json", is_flag=True, help="Print the full report as JSON.")
@click.option(
    "--write", "write_to", default=None, type=click.Path(dir_okay=False),
    help="Write the setup with the proposed windows to this file (only on a mismatch).",
)
def check(measurement, setup, as_json, write_to):
    """Check the windows of --setup against MEASUREMENT."""
    rep = api.check(measurement, setup)
    if as_json:
        click.echo(json.dumps(rep, indent=2))
    else:
        click.echo(f"{rep['status']}: {rep['summary']}")
        for issue in rep["issues"]:
            click.echo(f"  [{issue['severity']}] {issue['message']}")
        if rep["mismatch"] and rep["proposal"]:
            click.echo("proposed:")
            for line in _windows_lines({**rep["detection"], "windows": rep["proposal"]}):
                click.echo(line)
    if write_to and rep["mismatch"] and rep["proposal"]:
        fixed = api.apply_to_setup(api.load_setup(setup), rep)
        with open(write_to, "w", encoding="utf-8") as fh:
            json.dump(fixed, fh, indent=2)
        click.echo(f"wrote {write_to}")
    sys.exit(1 if rep["mismatch"] else 0)


def main() -> None:
    """``python -m chisurf.plugins.core.excitation_windows.cli.main``."""
    cli()


if __name__ == "__main__":
    main()
