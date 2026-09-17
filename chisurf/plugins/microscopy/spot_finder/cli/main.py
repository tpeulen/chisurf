"""CLI for spot and region detection in imaging data.

Usage::

    spot-finder detect FILE [FILE …]                     # the standard workflow
    spot-finder detect --workflow camera_spots FILE …
    spot-finder run recipe.json FILE [FILE …]
    spot-finder workflows
    spot-finder show single_molecule
    spot-finder list FILE
    spot-finder contract

``detect`` is the command line; ``run`` is the same thing described by a JSON
document, which is what a workflow that has to be reproduced, versioned or
shared should be. ``detect --save-workflow`` turns one into the other.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib

import click


@click.group()
def cli() -> None:
    """Detect spots and regions in imaging data, and persist what was found."""


@cli.command()
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "--workflow",
    "workflow_name",
    default="",
    help="Start from a shipped workflow (see `spot-finder workflows`); "
    "the options below then override it. Default: single_molecule.",
)
@click.option(
    "--save-workflow",
    "save_workflow",
    default="",
    type=click.Path(),
    help="Write the resolved settings out as a workflow JSON.",
)
@click.option(
    "--method",
    default="watershed",
    type=click.Choice(["watershed", "threshold", "log", "dog"]),
    help="Detector. watershed splits touching objects; log/dog measure width.",
)
@click.option("--name", default="spots", help="Stem the raster/table pair is written under.")
@click.option("--sigma", default=1.0, type=float, help="Pre-threshold Gaussian smoothing.")
@click.option(
    "--threshold",
    default=-1.0,
    type=float,
    help="Intensity level (<0 = Otsu); for log/dog, the minimum response.",
)
@click.option(
    "--peak-footprint-size",
    default=6,
    type=int,
    help="Watershed seed footprint; larger merges nearby seeds.",
)
@click.option("--min-area", default=1, type=int, help="Smallest region to keep (pixels).")
@click.option("--max-area", default=0, type=int, help="Largest region to keep; 0 disables.")
@click.option(
    "--clear-border/--keep-border", default=True, help="Drop regions touching the frame edge."
)
@click.option("--min-sigma", default=1.0, type=float, help="Smallest spot width (log/dog).")
@click.option("--max-sigma", default=5.0, type=float, help="Largest spot width (log/dog).")
@click.option("--num-sigma", default=10, type=int, help="Scales between them (log).")
@click.option("--overlap", default=0.5, type=float, help="Blob merge threshold (log/dog).")
@click.option(
    "--roi",
    "roi_path",
    default="",
    type=click.Path(),
    help="Confine the search: a saved region JSON, a mask or a label image.",
)
@click.option("--channels", default="", help="Routing channels for a photon file, comma-separated.")
@click.option("--frame", default=-1, type=int, help="Frame to detect in; -1 sums over frames.")
@click.option("--dry-run", is_flag=True, help="Detect and report, writing nothing.")
@click.option("--out-dir", default="", help="Directory for the containers.")
@click.option("--json", "json_output", is_flag=True, help="Print the run table as JSON.")
@click.pass_context
def detect(
    ctx,
    files,
    workflow_name,
    save_workflow,
    name,
    roi_path,
    channels,
    frame,
    dry_run,
    out_dir,
    json_output,
    **overrides,
) -> None:
    """Detect regions in FILES and write each into its measurement's container.

    Without ``--workflow`` this is the standard single-molecule segmentation.
    With one, the named workflow supplies every setting and the options below
    override only what is actually typed — an option left alone keeps the
    workflow's value rather than silently reimposing the command line's default,
    which is the difference between "start from camera_spots" meaning anything
    and meaning nothing.
    """
    from ..api.spot_finder import detect_request
    from ..core.workflow import STANDARD, request_from_workflow, workflow_from_request

    request = request_from_workflow(workflow_name or STANDARD, files=list(files))
    request.name = name
    request.frame = frame
    request.write = not dry_run
    request.out_dir = out_dir
    request.channels = [int(c) for c in channels.split(",") if c.strip()] or None

    # Only what the user actually typed. Click knows the difference; a plain
    # default cannot, and applying all of them would make --workflow decorative.
    for option, value in overrides.items():
        if ctx.get_parameter_source(option) is click.core.ParameterSource.COMMANDLINE:
            setattr(request.settings, option, value)

    if roi_path:
        from chisurf.core.roi.io import load_region

        # Several regions arriving as their union, which is what a saved
        # multi-region file means when it is used as an analysis area.
        request.settings.roi = load_region(roi_path)

    if save_workflow:
        pathlib.Path(save_workflow).write_text(
            json.dumps(workflow_from_request(request), indent=2) + "\n"
        )
        click.echo(f"workflow written to {save_workflow}", err=True)

    result = detect_request(
        request,
        progress=None if json_output else _echo_progress,
    )
    _report(result, json_output)

    # Non-zero when nothing was detected anywhere: a batch that found nothing is
    # a batch a script should notice, and "it ran" is not the same as "it worked".
    if not result.ok:
        raise SystemExit(1)


@cli.command()
@click.argument("recipe", type=click.Path(exists=True))
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--out-dir", default="", help="Directory for the containers.")
@click.option("--dry-run", is_flag=True, help="Detect and report, writing nothing.")
@click.option("--json", "json_output", is_flag=True, help="Print the run table as JSON.")
def run(recipe, files, out_dir, dry_run, json_output) -> None:
    """Run the detection described by the workflow document RECIPE.

    FILES override the document's own input list, which is the usual way round:
    a recipe says *how* to detect and is worth committing beside an analysis,
    while *what* to detect in changes with every dataset.
    """
    from ..api.spot_finder import detect_request
    from ..core.workflow import request_from_workflow

    request = request_from_workflow(recipe, files=list(files) or None, out_dir=out_dir)
    if dry_run:
        request.write = False
    if not request.files:
        raise click.UsageError(
            "no files: give them on the command line or in the document's "
            '"inputs": {"files": [...]}'
        )

    result = detect_request(request, progress=None if json_output else _echo_progress)
    _report(result, json_output)
    if not result.ok:
        raise SystemExit(1)


@cli.command()
@click.option("--json", "json_output", is_flag=True, help="Print as JSON.")
def workflows(json_output: bool) -> None:
    """List the shipped detection workflows, the standard one first."""
    from ..core.workflow import builtin_workflow, list_workflows

    names = list_workflows()
    if json_output:
        click.echo(json.dumps({name: builtin_workflow(name) for name in names}, indent=2))
        return
    for name in names:
        document = builtin_workflow(name)
        summary = (document.get("description") or "").split(".")[0]
        click.echo(f"{name:<16} {summary}.")


@cli.command()
@click.argument("name", default="")
def show(name: str) -> None:
    """Print a shipped workflow document, to start a recipe of your own from."""
    from ..core.workflow import STANDARD, builtin_workflow

    click.echo(json.dumps(builtin_workflow(name or STANDARD), indent=2))


@cli.command(name="list")
@click.argument("file", type=click.Path(exists=True))
def list_detections(file) -> None:
    """List the detections held in FILE's container."""
    from chisurf.core.fio.fluorescence.region_container import (
        list_region_sets,
        read_regions,
    )

    names = list_region_sets(file)
    if not names:
        click.echo("no detections")
        raise SystemExit(1)
    for name in names:
        regions = read_regions(file, name=name)
        click.echo(f"{name}: {regions.n_regions} region(s)")


@cli.command()
@click.option("--json", "json_output", is_flag=True, help="Print as JSON.")
def contract(json_output: bool) -> None:
    """Print the RPC contract."""
    from ..api.contract import contract_descriptor

    descriptor = contract_descriptor()
    if json_output:
        click.echo(json.dumps(descriptor, indent=2))
    else:
        for method in descriptor.get("methods", []):
            click.echo(method)


def _echo_progress(index: int, total: int, name: str) -> None:
    click.echo(f"[{index + 1}/{total}] {name}", err=True)


def _report(result, json_output: bool) -> None:
    """Print the run table — every input, whatever became of it."""
    if json_output:
        click.echo(
            json.dumps(
                {
                    "rows": [dataclasses.asdict(r) for r in result.rows],
                    "n_regions": result.n_regions,
                },
                indent=2,
            )
        )
        return
    for row in result.rows:
        suffix = f" — {row.reason}" if row.reason else ""
        click.echo(f"{row.status:<8}{row.n_regions:>7}  {row.input}{suffix}")
    click.echo(f"{result.n_regions} region(s) in {len(result.ok)}/{len(result.rows)} file(s)")
