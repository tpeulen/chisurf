from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

import click

from chisurf.plugins.quenching_estimator.api import local as api
from chisurf.plugins.quenching_estimator.core.project import (
    ProjectValidationError,
    template_project,
    validate_project,
)
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


def _clone_with_overrides(
    project: MutableMapping[str, Any], setters: Sequence[tuple[str, Any]]
) -> MutableMapping[str, Any]:
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


def _build_runs(
    base_project: MutableMapping[str, Any], setters: Sequence[tuple[str, Any]]
) -> list[tuple[MutableMapping[str, Any], dict[str, Any]]]:
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

    report = purge_runs(project_dir, older_than_days=older_than_days, dry_run=not confirmed)
    megabytes = report["bytes"] / (1024 * 1024)
    verb = "Would remove" if report["dry_run"] else "Removed"
    click.echo(f"{verb} {report['count']} run(s), {megabytes:.1f} MB from {report['directory']}")
    if report["dry_run"] and report["count"]:
        click.echo("Nothing was deleted. Pass --yes to do it.")


# -- the quenching analysis ---------------------------------------------------------------

_ANALYSIS_FORMATS = ("table", "json", "csv")


def _fit_overrides(preset: str | None, assignments: Sequence[str]) -> dict[str, Any]:
    """``KEY=VALUE`` fit settings as overrides; a dotted key edits a nested setting.

    ``profile_likelihood.points=3`` replaces only ``points`` of the preset's
    ``profile_likelihood`` (the engine replaces whole top-level keys).
    """
    from copy import deepcopy

    from chisurf.plugins.quenching_estimator.core.inference import graph_fit

    base = graph_fit.settings(preset)
    overrides: dict[str, Any] = {}
    for item in assignments:
        if "=" not in item:
            raise click.BadParameter(f"{item!r}: expected KEY=VALUE", param_hint="--set")
        key, raw = item.split("=", 1)
        top, _, rest = key.strip().partition(".")
        if top not in base:
            raise click.BadParameter(
                f"{top!r} is not a declared fit setting ({', '.join(sorted(base))})",
                param_hint="--set")
        if rest:
            value = overrides.get(top, deepcopy(base[top]))
            if not isinstance(value, dict):
                raise click.BadParameter(f"{top!r} has no nested settings", param_hint="--set")
            _set_path(value, rest, _parse_value(raw))
            overrides[top] = value
        else:
            overrides[top] = _parse_value(raw)
    return overrides


def _format_rows(table: Any) -> str:
    """A record array as aligned text columns (for reading, not for parsing)."""

    names = list(table.dtype.names)

    def cell(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:.4g}"
        return str(value)

    rows = [[cell(v) for v in record.tolist()] for record in table]
    widths = [max([len(n)] + [len(r[i]) for r in rows]) for i, n in enumerate(names)]
    lines = ["  ".join(n.ljust(w) for n, w in zip(names, widths))]
    lines += ["  ".join(v.ljust(w) for v, w in zip(r, widths)) for r in rows]
    return "\n".join(lines)


@cli.command("analyse")
@click.option(
    "--data",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Measurement folder (site lifetimes, titration points, titration summary CSVs). Default: the shipped MalE data.",
)
@click.option(
    "--stage",
    "stage_names",
    multiple=True,
    help="Stage to run (repeatable): A, B, naive_h2o, C, summary, or all (default). A stage also runs what it needs.",
)
@click.option(
    "--preset",
    type=str,
    default=None,
    help="Fit preset: full (64 searches) or quick (8 short searches, a test run).",
)
@click.option("--quick", is_flag=True, default=False, help="Shorthand for --preset quick.")
@click.option(
    "--set",
    "assignments",
    multiple=True,
    metavar="KEY=VALUE",
    help="Replace a declared fit setting (repeatable), e.g. --set n_starts=4 --set profile_likelihood.points=3.",
)
@click.option("--workers", type=int, default=None, help="Worker processes (1 = in process). Default: the CPU count.")
@click.option("--no-profile", is_flag=True, default=False, help="Skip the profile likelihoods.")
@click.option(
    "--structure",
    "structure_items",
    multiple=True,
    metavar="STATE=PATH",
    help="Structure of a state for the site tables (repeatable). Default: the shipped MalE structures.",
)
@click.option(
    "--tables",
    "tables_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help='JSON file {"STATE:site:linker_length": npz path} of stored site tables to use instead of building them.',
)
@click.option(
    "--cache-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Site-table cache folder.",
)
@click.option(
    "--output",
    "-o",
    "output_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Write the declared tables (<stage>.<table>.csv), summary.json, report.md and run.json here. Default: a run directory under the per-user artefact root.",
)
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Put the run directory under this project's jobs/ instead.",
)
@click.option("--no-save", is_flag=True, default=False, help="Write nothing; only print.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(_ANALYSIS_FORMATS),
    default="table",
    show_default=True,
    help="table: titles, texts and estimates; json: the full summary; csv: one declared table (--table).",
)
@click.option(
    "--table",
    "table_name",
    default=None,
    help="Table printed by --format csv, as <stage>.<table> (default: the last stage's estimates).",
)
@click.option("--quiet", "-q", is_flag=True, default=False, help="No progress on stderr.")
def analyse(
    data: Path | None,
    stage_names: Sequence[str],
    preset: str | None,
    quick: bool,
    assignments: Sequence[str],
    workers: int | None,
    no_profile: bool,
    structure_items: Sequence[str],
    tables_file: Path | None,
    cache_dir: Path | None,
    output_dir: Path | None,
    project_dir: Path | None,
    no_save: bool,
    output_format: str,
    table_name: str | None,
    quiet: bool,
) -> None:
    """Run the quenching analysis (the inverse fit of measured site lifetimes).

    Examples: `csc quest analyse --quick --stage B -o out/` runs heavy-water Atto655 only;
    `csc quest analyse --stage all --format json` prints the full summary.
    """

    import sys
    import tempfile

    from chisurf.plugins.quenching_estimator.core import runs as _runs
    from chisurf.plugins.quenching_estimator.core.inference import graph_fit
    from chisurf.plugins.quenching_estimator.core.inference import stages as _stages

    if quick:
        if preset not in (None, "quick"):
            raise click.BadParameter("--quick contradicts --preset", param_hint="--quick")
        preset = "quick"
    if preset is not None and preset not in graph_fit.preset_names():
        raise click.BadParameter(
            f"{preset!r}; declared: {', '.join(graph_fit.preset_names())}", param_hint="--preset")
    declared = _stages.stage_names()
    names = [n for n in stage_names if n != "all"]
    if not names or "all" in stage_names:
        stages: Any = "all"
    else:
        unknown = [n for n in names if n not in declared]
        if unknown:
            raise click.BadParameter(
                f"{unknown}; declared: {', '.join(declared)}", param_hint="--stage")
        stages = names
    overrides = _fit_overrides(preset, assignments)
    structures = {}
    for item in structure_items:
        state, sep, path = item.partition("=")
        if not sep:
            raise click.BadParameter(f"{item!r}: expected STATE=PATH", param_hint="--structure")
        structures[state] = path
    tables = None
    if tables_file is not None:
        tables = json.loads(tables_file.read_text(encoding="utf8"))

    def progress(percent: int, message: str) -> None:
        if not quiet:
            click.echo(f"[{percent:3d}%] {message}", err=True)

    try:
        entry = _runs.analyse(
            stages, data=data, structures=structures or None, tables=tables,
            cache_dir=cache_dir, preset=preset, fit_overrides=overrides or None,
            workers=workers, profile=not no_profile, output=output_dir,
            project_dir=project_dir, save_outputs=not no_save, progress=progress,
        )
    except (KeyError, ValueError, FileNotFoundError) as exc:
        raise click.ClickException(str(exc))
    result = entry["result"]

    if output_format == "json":
        from chisurf.plugins.quenching_estimator.rpc.services import analysis_payload

        payload = analysis_payload(result)
        payload["run"] = {k: entry[k] for k in ("run_id", "directory", "files")}
        click.echo(json.dumps(payload, indent=1))
    elif output_format == "csv":
        tables_out = result.tables()
        name = table_name or f"{list(result.stages)[-1]}.estimates"
        if name not in tables_out:
            raise click.ClickException(
                f"No table {name!r}; this run has {', '.join(sorted(tables_out))}")
        # The declared writer, so stdout carries exactly the file format.
        if entry["directory"]:
            path = Path(entry["directory"]) / f"{name}.csv"
            sys.stdout.write(path.read_text(encoding="utf-8"))
        else:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"{name}.csv"
                _stages.write_csv(tables_out[name], path)
                sys.stdout.write(path.read_text(encoding="utf-8"))
    else:
        for stage in result.stages.values():
            click.echo(f"## {stage.title}\n")
            if stage.text:
                click.echo(stage.text + "\n")
            if "estimates" in stage.tables and len(stage.tables["estimates"]):
                click.echo(_format_rows(stage.tables["estimates"]) + "\n")
    if entry["directory"] and not quiet:
        click.echo(f"Wrote {len(entry['files'])} files to {entry['directory']}", err=True)


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
        fret_counts = (
            result.fret_counts if result.fret_counts is not None else [None] * len(result.time)
        )
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
