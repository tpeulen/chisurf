from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

import json

import click

from chisurf.plugins.quenching_estimator.api import local as api
from chisurf.plugins.quenching_estimator.core.project import ProjectValidationError, template_project, validate_project
from chisurf.plugins.quenching_estimator.core.scan import simulate_site
from chisurf.plugins.quenching_estimator.core.structure import resolve_structure_path


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="chisurf", prog_name="quest")
def cli() -> None:
    """Command line interface for QuEst (Quenching Estimator)."""


def _parse_value(raw: str) -> Any:
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered == "null" or lowered == "none":
        return None
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def _set_path(target: MutableMapping[str, Any], path: str, value: Any) -> None:
    """Set dotted path inside a mapping, creating nested dicts or list indices as needed."""
    parts = path.split(".")
    cursor: Any = target
    for i, key in enumerate(parts[:-1]):
        next_key = parts[i + 1]
        if next_key.isdigit():
            if key not in cursor or not isinstance(cursor[key], list):
                cursor[key] = []
            cursor = cursor[key]
        elif isinstance(cursor, list) and key.isdigit():
            idx = int(key)
            while len(cursor) <= idx:
                cursor.append({})
            if not isinstance(cursor[idx], dict):
                cursor[idx] = {}
            cursor = cursor[idx]
        else:
            if key not in cursor or not isinstance(cursor[key], dict):
                cursor[key] = {}
            cursor = cursor[key]

    last_key = parts[-1]
    if isinstance(cursor, list) and last_key.isdigit():
        idx = int(last_key)
        while len(cursor) <= idx:
            cursor.append(None)
        cursor[idx] = value
    else:
        cursor[last_key] = value


def _clone_with_overrides(project: MutableMapping[str, Any], setters: Sequence[tuple[str, Any]]) -> MutableMapping[str, Any]:
    from copy import deepcopy

    clone = deepcopy(project)
    for key, val in setters:
        _set_path(clone, key, val)
    return clone


def _expand_grid(setters: Sequence[tuple[str, Any]]) -> Sequence[tuple[str, Any]]:
    """Expand comma-separated values into multiple setter entries."""
    expanded: list[tuple[str, Any]] = []
    for key, raw in setters:
        if isinstance(raw, str) and "," in raw:
            expanded.append((key, [_parse_value(v) for v in raw.split(",")]))
        else:
            expanded.append((key, raw))
    return expanded


def _cartesian(assignments: Sequence[tuple[str, Sequence[Any]]]) -> list[list[tuple[str, Any]]]:
    if not assignments:
        return [[]]
    head_key, head_vals = assignments[0]
    rest = assignments[1:]
    tails = _cartesian(rest)
    combos: list[list[tuple[str, Any]]] = []
    for hv in head_vals:
        for t in tails:
            combos.append([(head_key, hv)] + t)
    return combos


def _build_runs(base_project: MutableMapping[str, Any], setters: Sequence[tuple[str, Any]]) -> list[tuple[MutableMapping[str, Any], dict[str, Any]]]:
    """Create per-run projects for grid sweeping."""
    # Split single vs multi-valued
    multi: list[tuple[str, list[Any]]] = []
    singles: list[tuple[str, Any]] = []
    for key, val in setters:
        if isinstance(val, list):
            multi.append((key, val))
        else:
            singles.append((key, val))

    if not multi:
        proj = _clone_with_overrides(base_project, singles)
        return [(proj, {k: v for k, v in singles})]

    combos = _cartesian(multi)
    runs: list[tuple[MutableMapping[str, Any], dict[str, Any]]] = []
    for combo in combos:
        effective = singles + combo
        proj = _clone_with_overrides(base_project, effective)
        tag = {k: v for k, v in combo}
        tag.update({k: v for k, v in singles})
        runs.append((proj, tag))
    return runs


def _sanitize_tag_value(val: Any) -> str:
    txt = str(val)
    return txt.replace("/", "_").replace("\\", "_").replace(" ", "_")


def _resolve_output_path(
    *,
    output_path: Path | None,
    project_path: Path,
    idx: int,
    tags: Mapping[str, Any],
    multiple: bool,
) -> Path:
    base = output_path
    if base is None:
        base = project_path.with_suffix(".csv")
    stem = base.stem
    suffix = base.suffix or ".csv"

    if multiple:
        tag_parts = [f"{k}-{_sanitize_tag_value(v)}" for k, v in sorted(tags.items())]
        tag_block = "_".join(tag_parts) if tag_parts else f"run{idx}"
        stem = f"{stem}_{tag_block}"
    return base.with_name(stem + suffix)


@cli.command()
@click.option(
    "-p",
    "--project",
    "project_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to a QuEst project JSON file.",
)
@click.option(
    "--pdb",
    "pdb_path",
    required=False,
    type=str,
    help="Override structure path or PDB ID instead of project['pdb'].",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    required=False,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Output path. Uses extension to choose format (csv|json).",
)
@click.option(
    "--nbins",
    type=int,
    default=None,
    help="Number of histogram bins. Defaults to project value or 4096.",
)
@click.option(
    "--tac-start",
    type=float,
    default=0.0,
    show_default=True,
    help="Start of TAC range in ns.",
)
@click.option(
    "--tac-stop",
    type=float,
    default=50.0,
    show_default=True,
    help="End of TAC range in ns.",
)
@click.option(
    "--set",
    "set_param",
    multiple=True,
    help="Override project value, dotted path (e.g., fret.enabled=false or attachment.residue=42).",
)
@click.option(
    "--grid",
    "grid_param",
    multiple=True,
    help="Sweep multiple values, dotted path with comma list (e.g., attachment.residue=42,43,44).",
)
def simulate(
    project_path: Path,
    pdb_path: str | None,
    output_path: Path | None,
    nbins: int | None,
    tac_start: float,
    tac_stop: float,
    set_param: tuple[str, ...] = (),
    grid_param: tuple[str, ...] = (),
) -> None:
    """Run a QuEst project headlessly and write decay results."""

    try:
        base_project = api.load_project(project_path)
    except Exception as exc:  # pragma: no cover - defensive
        raise click.ClickException(f"Failed to load project: {exc}")

    setters: list[tuple[str, Any]] = []
    for raw in set_param:
        if "=" not in raw:
            raise click.ClickException(f"--set expects key=value, got: {raw}")
        key, value = raw.split("=", 1)
        setters.append((key, _parse_value(value)))
    for raw in grid_param:
        if "=" not in raw:
            raise click.ClickException(f"--grid expects key=val1,val2, got: {raw}")
        key, value = raw.split("=", 1)
        setters.append((key, [_parse_value(v) for v in value.split(",")]))

    runs = _build_runs(base_project, setters)
    results_written = []

    from chisurf.core.runtime.progress import progress

    items = runs if len(runs) <= 1 else progress(runs, desc="Simulating grid")
    for idx, (project, tags) in enumerate(items):
        _validate_project(project, project_path, pdb_path=pdb_path)

        try:
            result = api.simulate_project(
                project,
                pdb_path=pdb_path,
                nbins=nbins,
                tac_range=(tac_start, tac_stop),
                project_dir=project_path.parent,
                # Explicit since 2026-07-28: `save_outputs` defaults to False,
                # and the CLI is one of the two surfaces whose user asked for a
                # run record. Next to the project, because that is where a CLI
                # user looks for it.
                save_outputs=True,
            )
        except Exception as exc:  # pragma: no cover - defensive
            raise click.ClickException(f"Simulation failed: {exc}")

        out_path = _resolve_output_path(
            output_path=output_path,
            project_path=project_path,
            idx=idx,
            tags=tags,
            multiple=len(runs) > 1,
        )

        suffix = out_path.suffix.lower()
        if suffix == ".csv":
            _write_csv(out_path, result)
        elif suffix == ".json":
            _write_json(out_path, result)
        else:
            raise click.ClickException("Output must end with .csv or .json")

        results_written.append(str(out_path))

    if len(results_written) == 1:
        click.echo(f"Wrote results to {results_written[0]}")
    else:
        click.echo("Wrote results:\n" + "\n".join(f"  - {p}" for p in results_written))


@cli.command()
@click.option(
    "-o",
    "--output",
    "output_path",
    required=False,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write template to file (default: stdout).",
)
@click.option(
    "--with-fret/--no-fret",
    default=True,
    show_default=True,
    help="Include FRET configuration.",
)
def template(output_path: Path | None, with_fret: bool) -> None:
    """Emit a minimal QuEst project template."""

    project = template_project(with_fret=with_fret)
    payload = json.dumps(project, indent=2)

    if output_path:
        output_path.write_text(payload, encoding="utf8")
        click.echo(f"Wrote template to {output_path}")
    else:
        click.echo(payload)


@cli.command()
@click.option(
    "-p",
    "--project",
    "project_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to a QuEst project JSON file.",
)
def validate(project_path: Path) -> None:
    """Validate a project JSON file and report issues."""

    try:
        project = api.load_project(project_path)
    except Exception as exc:  # pragma: no cover - defensive
        raise click.ClickException(f"Failed to load project: {exc}")

    _validate_project(project, project_path)
    click.echo(f"{project_path} is valid.")


@cli.command()
@click.option(
    "-p",
    "--project",
    "project_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to a QuEst project JSON file.",
)
@click.option(
    "-l",
    "--labeling",
    "labeling_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to an fps.json file defining labeling sites.",
)
@click.option(
    "--pdb",
    "pdb_path",
    required=False,
    type=str,
    help="Override structure path or PDB ID instead of project['pdb'].",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Output JSON file to write simulation results to.",
)
@click.option(
    "--nbins",
    type=int,
    default=None,
    help="Number of histogram bins.",
)
@click.option(
    "--tac-start",
    type=float,
    default=0.0,
    show_default=True,
    help="Start of TAC range in ns.",
)
@click.option(
    "--tac-stop",
    type=float,
    default=50.0,
    show_default=True,
    help="End of TAC range in ns.",
)
def scan(
    project_path: Path,
    labeling_path: Path,
    pdb_path: str | None,
    output_path: Path,
    nbins: int | None,
    tac_start: float,
    tac_stop: float,
) -> None:
    """Run accessible volume and quenching simulations for multiple sites in an fps.json file."""

    try:
        project = api.load_project(project_path)
    except Exception as exc:
        raise click.ClickException(f"Failed to load project: {exc}")

    try:
        fps_data = api.load_fps_json(labeling_path)
    except Exception as exc:
        raise click.ClickException(f"Failed to load labeling fps.json: {exc}")

    resolved_pdb: Path | None = None
    structure_source = pdb_path or project.get("pdb")
    if structure_source is not None:
        try:
            resolved_pdb = resolve_structure_path(structure_source)
        except Exception as exc:
            raise click.ClickException(str(exc)) from exc

    # The scan runs with save_outputs=False, so nothing is written here; the
    # path only exists because simulate_project takes a project directory.
    scan_temp_dir = output_path.parent

    positions = fps_data.get("Positions", {})
    if not positions:
        click.echo("No positions found in fps.json. Nothing to scan.")
        return

    results = {}
    from chisurf.core.runtime.progress import progress

    for name, pos in progress(list(positions.items()), desc="Scanning labeling sites"):
        res = simulate_site(
            project,
            pos,
            name=name,
            pdb_path=resolved_pdb,
            nbins=nbins,
            tac_range=(tac_start, tac_stop),
            project_dir=scan_temp_dir,
        )
        results[name] = res

    try:
        output_path.write_text(json.dumps(results, indent=2), encoding="utf8")
        click.echo(f"Wrote scan results to {output_path}")
    except Exception as exc:
        raise click.ClickException(f"Failed to write output file: {exc}")


@cli.group()
def runs() -> None:
    """Inspect and tidy the run artefacts a simulation leaves behind.

    Named `runs`, not `jobs`: a *job* is a running operation (quest.jobs.*),
    and the two meant the same word until 2026-07-28.
    """


@runs.command("clean")
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Clean this project's jobs/ instead of the per-user artefact root.",
)
@click.option(
    "--older-than",
    "older_than_days",
    type=float,
    default=None,
    help="Only remove runs untouched for this many days.",
)
@click.option(
    "--yes",
    "confirmed",
    is_flag=True,
    default=False,
    help="Actually delete. Without it this only reports what would go.",
)
def runs_clean(project_dir: Path | None, older_than_days: float | None, confirmed: bool) -> None:
    """Delete run directories. Reports without deleting unless --yes is given."""

    from chisurf.plugins.quenching_estimator.core.runs import purge_runs

    report = purge_runs(
        project_dir, older_than_days=older_than_days, dry_run=not confirmed
    )
    megabytes = report["bytes"] / (1024 * 1024)
    verb = "Would remove" if report["dry_run"] else "Removed"
    click.echo(f"{verb} {report['count']} run(s), {megabytes:.1f} MB from {report['directory']}")
    if report["dry_run"] and report["count"]:
        click.echo("Nothing was deleted. Pass --yes to do it.")


@cli.command()
def gui() -> None:
    """Launch the QuEst window (the native emtk app)."""

    from chisurf.plugins.quenching_estimator.__main__ import main

    raise SystemExit(main([]))


def _validate_project(
    project: Mapping[str, Any],
    project_path: Path | None = None,
    pdb_path: Path | str | None = None,
) -> None:
    """Validate a project, reporting failures the way Click expects.

    The rules live in :mod:`quest.project` so every surface enforces the same
    ones; this wrapper only translates the domain error into a
    ``ClickException``.
    """

    try:
        validate_project(project, project_path=project_path, pdb_path=pdb_path)
    except ProjectValidationError as exc:
        raise click.ClickException(str(exc)) from exc


def _write_csv(path: Path, result: api.DecaySimulationResult) -> None:
    import csv

    fieldnames = [
        "time_ns",
        "donor_counts",
        "fret_counts",
        "quantum_yield_donor",
        "quantum_yield_fret",
        "collisions_fraction",
        "fret_efficiency",
    ]
    with path.open("w", newline="", encoding="utf8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        fret_counts = result.fret_counts if result.fret_counts is not None else [None] * len(result.time)
        for t, d, f in zip(result.time, result.donor_counts, fret_counts):
            writer.writerow(
                {
                    "time_ns": float(t),
                    "donor_counts": float(d),
                    "fret_counts": None if f is None else float(f),
                    "quantum_yield_donor": result.quantum_yield_donor,
                    "quantum_yield_fret": result.quantum_yield_fret,
                    "collisions_fraction": result.collisions_fraction,
                    "fret_efficiency": result.fret_efficiency,
                }
            )


def _write_json(path: Path, result: api.DecaySimulationResult) -> None:
    payload = {
        "time_ns": result.time.tolist(),
        "donor_counts": result.donor_counts.tolist(),
        "fret_counts": None if result.fret_counts is None else result.fret_counts.tolist(),
        "quantum_yield_donor": result.quantum_yield_donor,
        "quantum_yield_fret": result.quantum_yield_fret,
        "collisions_fraction": result.collisions_fraction,
        "fret_efficiency": result.fret_efficiency,
        "project": result.project,
        "aa_residence": getattr(result, "aa_residence", []),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf8")


#: Kept as a module-level alias so existing callers keep working; the template
#: itself is domain logic and lives in :mod:`quest.project`.
_template_project = template_project


if __name__ == "__main__":
    cli()
