#!/usr/bin/env python3
"""Qt-free ndXplorer workflows with explicit MMFDB provenance boundaries."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import click

logger = logging.getLogger(__name__)

SubprocessRunner = Callable[..., subprocess.CompletedProcess[str]]


def _get_ndxplorer_env() -> dict[str, str]:
    """Return an environment that can import the optional ndXplorer module."""
    env = dict(os.environ)
    root = Path(__file__).resolve().parents[3]
    ndx_path = root / "modules" / "ndxplorer"
    python_path = env.get("PYTHONPATH", "")
    entries = [entry for entry in python_path.split(os.path.pathsep) if entry]
    if str(ndx_path) not in entries:
        entries.insert(0, str(ndx_path))
    env["PYTHONPATH"] = os.path.pathsep.join(entries)
    return env


def _parse_command_result(command: str, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """Validate an ndXplorer subprocess result and extract its JSON object."""
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "no diagnostic output").strip()
        raise RuntimeError(f"ndXplorer {command} failed: {detail}")

    output = (result.stdout or "").strip()
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        start = output.find("{")
        end = output.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError(
                f"ndXplorer {command} returned no JSON object: {output!r}"
            ) from None
        try:
            payload = json.loads(output[start : end + 1])
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"ndXplorer {command} returned invalid JSON: {output!r}"
            ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"ndXplorer {command} returned a non-object JSON payload")
    return payload


def resolve_source_artifact(db: Any, artifact_id: str, *, principal: Any) -> str:
    """Resolve a source artifact through an explicit MMFDB client.

    The caller must supply an authenticated principal. The ACL check happens
    before the artifact path is disclosed or materialized.
    """
    from mmfdb.security.auth import AuthError, require_authenticated

    if principal is None:
        raise AuthError("Authentication required")
    require_authenticated(principal)
    if not artifact_id:
        raise ValueError("source artifact ID is required")
    conn = getattr(db, "conn", None)
    if conn is None:
        raise TypeError("ACL enforcement requires an MMFDB client with a connection")
    from mmfdb.security.auth import PERM_READ, require_access

    require_access(conn, principal, "artifact", artifact_id, PERM_READ)

    local_path = db.open_dataset(artifact_id)
    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(f"resolved source artifact is unavailable: {artifact_id}")
    if path.is_file() and not os.access(path, os.R_OK):
        raise PermissionError(f"resolved source artifact is not readable: {artifact_id}")
    return str(path)


def _authenticate_cli_token(db: Any, token: str) -> Any:
    """Authenticate one CLI token without falling back to a configured user."""
    from mmfdb.security.auth import authenticate_token, require_authenticated

    principal = authenticate_token(db.conn, token)
    require_authenticated(principal)
    return principal


def _execute_ndxplorer(
    command: str,
    arguments: list[str],
    *,
    subprocess_runner: SubprocessRunner,
) -> dict[str, Any]:
    args = [sys.executable, "-m", "ndxplorer", command, *arguments]
    logger.info("Running ndXplorer %s", command)
    completed = subprocess_runner(
        args,
        capture_output=True,
        text=True,
        env=_get_ndxplorer_env(),
        check=False,
    )
    return _parse_command_result(command, completed)


def _common_metadata(
    *,
    source_artifact_id: str,
    selections: Iterable[str],
    query: str | None,
    skip_nth_row: int,
) -> dict[str, Any]:
    return {
        "source_artifact_id": source_artifact_id,
        "selections": list(selections),
        "query": query,
        "skip_nth_row": skip_nth_row,
        "software_module": "ndxplorer",
    }


def _register_filter_output(
    db: Any,
    *,
    source_artifact_id: str,
    output_path: Path,
    sample_id: str,
    metadata: dict[str, Any],
    session: Any,
) -> str:
    from mmfdb.provenance.result_registry import register_result

    with db.transaction():
        return register_result(
            kind="external_reference",
            data=None,
            sample_id=sample_id,
            parent_artifact_id=source_artifact_id,
            operation_type="burst_filtering",
            metadata={
                **metadata,
                "path": str(output_path.resolve()),
                "folder_path": str(output_path.resolve()),
                "output_role": "filtered_burst_selection",
            },
            data_format="directory",
            db=db,
            session=session,
        )


def run_filter_workflow(
    *,
    db: Any,
    source_artifact_id: str,
    output_path: str | os.PathLike[str] | None = None,
    selections: Iterable[str] = (),
    query: str | None = None,
    skip_nth_row: int = 1,
    sample_id: str = "",
    register_output: bool = False,
    principal: Any,
    subprocess_runner: SubprocessRunner = subprocess.run,
) -> dict[str, Any]:
    """Filter a burst selection using an explicitly owned MMFDB client."""
    if skip_nth_row < 1:
        raise ValueError("skip_nth_row must be at least 1")
    selections = tuple(selections)
    source_path = Path(resolve_source_artifact(db, source_artifact_id, principal=principal))
    from mmfdb.security.session import SessionContext

    session = SessionContext(
        user_id=principal.user_id,
        db=db,
        is_admin=principal.is_admin,
    )
    target = (
        Path(output_path)
        if output_path
        else source_path.parent / f"{source_path.name}_filtered"
    )
    arguments = [
        "--folder",
        str(source_path),
        "--out",
        str(target),
        "--skip-nth-row",
        str(skip_nth_row),
    ]
    for selection in selections:
        arguments.extend(("--select", selection))
    if query:
        arguments.extend(("--query", query))
    payload = _execute_ndxplorer("filter", arguments, subprocess_runner=subprocess_runner)
    for required in ("n_in", "n_out", "out"):
        if required not in payload:
            raise RuntimeError(f"ndXplorer filter result is missing {required!r}")

    artifact_id: str | None = None
    if register_output:
        if not target.is_dir():
            raise FileNotFoundError(f"ndXplorer filter output was not created: {target}")
        metadata = {
            **_common_metadata(
                source_artifact_id=source_artifact_id,
                selections=selections,
                query=query,
                skip_nth_row=skip_nth_row,
            ),
            "n_in": payload["n_in"],
            "n_out": payload["n_out"],
        }
        artifact_id = _register_filter_output(
            db,
            source_artifact_id=source_artifact_id,
            output_path=target,
            sample_id=sample_id,
            metadata=metadata,
            session=session,
        )
    return {
        "ok": True,
        "artifact_id": artifact_id,
        "n_in": payload["n_in"],
        "n_out": payload["n_out"],
        "out": payload["out"],
    }


def _register_image_outputs(
    db: Any,
    *,
    source_artifact_id: str,
    image_path: Path,
    selection_path: Path | None,
    sample_id: str,
    metadata: dict[str, Any],
    session: Any,
) -> tuple[str, str | None]:
    """Register all image workflow outputs in one MMFDB transaction."""
    # Import the module at call time so host applications can replace the
    # registry implementation without stale module-level state.
    from mmfdb.provenance import result_registry

    with db.transaction():
        image_artifact_id = result_registry.register_result(
            kind="processed_data",
            data=image_path,
            sample_id=sample_id,
            parent_artifact_id=source_artifact_id,
            operation_type="image_analysis",
            metadata={
                **metadata,
                "output_path": str(image_path.resolve()),
                "output_role": "parameter_map",
            },
            db=db,
            session=session,
        )
        selection_artifact_id: str | None = None
        if selection_path is not None:
            selection_artifact_id = result_registry.register_result(
                kind="external_reference",
                data=None,
                sample_id=sample_id,
                parent_artifact_id=source_artifact_id,
                operation_type="filtering",
                metadata={
                    **metadata,
                    "path": str(selection_path.resolve()),
                    "folder_path": str(selection_path.resolve()),
                    "output_role": "roi_burst_selection",
                },
                data_format="directory",
                db=db,
                session=session,
            )
    return image_artifact_id, selection_artifact_id


def run_image_workflow(
    *,
    db: Any,
    source_artifact_id: str,
    map_parameter: str,
    output_path: str | os.PathLike[str],
    output_selection_path: str | os.PathLike[str] | None = None,
    selections: Iterable[str] = (),
    query: str | None = None,
    roi_path: str | os.PathLike[str] | None = None,
    skip_nth_row: int = 1,
    sample_id: str = "",
    register_outputs: bool = False,
    principal: Any,
    subprocess_runner: SubprocessRunner = subprocess.run,
) -> dict[str, Any]:
    """Render an image map and optional ROI selection without importing Qt."""
    if not map_parameter.strip():
        raise ValueError("map_parameter is required")
    if skip_nth_row < 1:
        raise ValueError("skip_nth_row must be at least 1")
    selections = tuple(selections)
    source_path = resolve_source_artifact(db, source_artifact_id, principal=principal)
    from mmfdb.security.session import SessionContext

    session = SessionContext(
        user_id=principal.user_id,
        db=db,
        is_admin=principal.is_admin,
    )
    target = Path(output_path)
    selection_target = Path(output_selection_path) if output_selection_path else None
    arguments = [
        "--file",
        source_path,
        "--map",
        map_parameter,
        "--out",
        str(target),
        "--skip-nth-row",
        str(skip_nth_row),
    ]
    for selection in selections:
        arguments.extend(("--select", selection))
    if query:
        arguments.extend(("--query", query))
    if roi_path is not None:
        arguments.extend(("--roi", str(roi_path)))
    if selection_target is not None:
        arguments.extend(("--out-selection", str(selection_target)))

    payload = _execute_ndxplorer("image", arguments, subprocess_runner=subprocess_runner)
    for required in ("shape", "n_selected_px", "out"):
        if required not in payload:
            raise RuntimeError(f"ndXplorer image result is missing {required!r}")

    image_artifact_id: str | None = None
    selection_artifact_id: str | None = None
    if register_outputs:
        if not target.is_file():
            raise FileNotFoundError(f"ndXplorer image output was not created: {target}")
        if selection_target is not None and not selection_target.is_dir():
            raise FileNotFoundError(
                f"ndXplorer ROI selection output was not created: {selection_target}"
            )
        metadata = {
            **_common_metadata(
                source_artifact_id=source_artifact_id,
                selections=selections,
                query=query,
                skip_nth_row=skip_nth_row,
            ),
            "map_parameter": map_parameter,
            "roi_path": str(Path(roi_path).resolve()) if roi_path is not None else None,
            "shape": payload["shape"],
            "n_selected_px": payload["n_selected_px"],
        }
        image_artifact_id, selection_artifact_id = _register_image_outputs(
            db,
            source_artifact_id=source_artifact_id,
            image_path=target,
            selection_path=selection_target,
            sample_id=sample_id,
            metadata=metadata,
            session=session,
        )

    return {
        "ok": True,
        "artifact_id": image_artifact_id,
        "selection_artifact_id": selection_artifact_id,
        "map": map_parameter,
        "shape": payload["shape"],
        "n_selected_px": payload["n_selected_px"],
        "out": payload["out"],
    }


@click.group()
def cli() -> None:
    """ndXplorer headless CLI with explicit MMFDB integration."""


@cli.command("filter")
@click.option("--from-mmfdb", required=True, help="Source MMFDB burst selection artifact ID.")
@click.option("--select", "selections", multiple=True, help="Selection format: param:min-max")
@click.option("--query", help="Pandas eval query string.")
@click.option("--out", type=click.Path(), help="Output folder.")
@click.option("--to-mmfdb/--no-to-mmfdb", default=False, show_default=True)
@click.option("--sample-id", default="", help="Existing MMFDB sample ID.")
@click.option(
    "--db",
    "db_path",
    required=True,
    type=click.Path(dir_okay=False),
    help="SQLite database path.",
)
@click.option(
    "--token",
    required=True,
    envvar="MMFDB_TOKEN",
    help="MMFDB session token (or set MMFDB_TOKEN).",
)
@click.option("--skip-nth-row", type=click.IntRange(min=1), default=1, show_default=True)
def filter_cmd(
    from_mmfdb: str,
    selections: tuple[str, ...],
    query: str | None,
    out: str | None,
    to_mmfdb: bool,
    sample_id: str,
    db_path: str,
    token: str,
    skip_nth_row: int,
) -> None:
    """Run parameter-based filtering on an MMFDB burst selection."""
    from mmfdb.repository import MFDatabase

    try:
        with MFDatabase(db_path) as db:
            principal = _authenticate_cli_token(db, token)
            result = run_filter_workflow(
                db=db,
                source_artifact_id=from_mmfdb,
                output_path=out,
                selections=selections,
                query=query,
                skip_nth_row=skip_nth_row,
                sample_id=sample_id,
                register_output=to_mmfdb,
                principal=principal,
            )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(result, indent=2))


@cli.command("image")
@click.option("--from-mmfdb", required=True, help="Source MMFDB image/TTTR artifact ID.")
@click.option("--map", "map_parameter", required=True, help="Parameter map to render.")
@click.option("--select", "selections", multiple=True, help="Selection format: param:min-max")
@click.option("--query", help="Pandas eval query string.")
@click.option("--roi", type=click.Path(exists=True), help="TIFF class-mask ROI.")
@click.option("--out", required=True, type=click.Path(), help="Rendered map output path.")
@click.option("--out-selection", type=click.Path(), help="Filtered burst-selection folder.")
@click.option("--to-mmfdb/--no-to-mmfdb", default=False, show_default=True)
@click.option("--sample-id", default="", help="Existing MMFDB sample ID.")
@click.option(
    "--db",
    "db_path",
    required=True,
    type=click.Path(dir_okay=False),
    help="SQLite database path.",
)
@click.option(
    "--token",
    required=True,
    envvar="MMFDB_TOKEN",
    help="MMFDB session token (or set MMFDB_TOKEN).",
)
@click.option("--skip-nth-row", type=click.IntRange(min=1), default=1, show_default=True)
def image_cmd(
    from_mmfdb: str,
    map_parameter: str,
    selections: tuple[str, ...],
    query: str | None,
    roi: str | None,
    out: str,
    out_selection: str | None,
    to_mmfdb: bool,
    sample_id: str,
    db_path: str,
    token: str,
    skip_nth_row: int,
) -> None:
    """Render a parameter map and optional ROI selection from MMFDB data."""
    from mmfdb.repository import MFDatabase

    try:
        with MFDatabase(db_path) as db:
            principal = _authenticate_cli_token(db, token)
            result = run_image_workflow(
                db=db,
                source_artifact_id=from_mmfdb,
                map_parameter=map_parameter,
                output_path=out,
                output_selection_path=out_selection,
                selections=selections,
                query=query,
                roi_path=roi,
                skip_nth_row=skip_nth_row,
                sample_id=sample_id,
                register_outputs=to_mmfdb,
                principal=principal,
            )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    cli()
