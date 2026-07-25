"""Agent tools for finding files on disk and loading them into ChiSurf."""

from __future__ import annotations

import logging
import pathlib
from typing import Any

import chisurf as cs
from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.spec import SAFETY_READ, SAFETY_WRITE, ToolError, ToolRegistry
from chisurf.core.agent.tools._dto import dataset_summary

logger = logging.getLogger(__name__)

registry = ToolRegistry()

#: File-extension → ``(experiment name, reader name)`` used to pick a reader
#: when the user does not name one.  Extensions absent here are still
#: loadable, they just need an explicit ``experiment``/``reader``.
EXTENSION_READERS: dict[str, tuple[str, str]] = {
    ".dat": ("TCSPC", "TXT/CSV"),
    ".txt": ("TCSPC", "TXT/CSV"),
    ".csv": ("TCSPC", "TXT/CSV"),
    ".ibh": ("TCSPC", "TXT/CSV"),
    ".pqres": ("TCSPC", "TXT/CSV"),
    ".thd": ("TCSPC", "TXT/CSV"),
    ".sdt": ("TCSPC", "Becker-SDT"),
    ".ptu": ("TCSPC", "TTTR-file"),
    ".ht3": ("TCSPC", "TTTR-file"),
    ".pt3": ("TCSPC", "TTTR-file"),
    ".spc": ("TCSPC", "TTTR-file"),
    ".cor": ("FCS", "Seidel Kristine"),
    ".sin": ("FCS", "Correlator.com SIN"),
    ".asc": ("FCS", "ALV-Correlator"),
    ".fcs": ("FCS", "Zeiss Confocor3"),
    ".dta": ("DEER", "DEER (BES3T/CSV)"),
    ".dsc": ("DEER", "DEER (BES3T/CSV)"),
    ".pdb": ("Modelling", "StructureReader"),
    ".cif": ("Modelling", "StructureReader"),
}

#: Extensions that are never experimental data.
_IGNORED_SUFFIXES = {".png", ".jpg", ".jpeg", ".pdf", ".py", ".json", ".yaml", ".yml", ".md"}


def guess_experiment(path: pathlib.Path) -> tuple[str, str] | None:
    """Return the ``(experiment, reader)`` guessed for a file, or ``None``.

    Parameters
    ----------
    path : pathlib.Path
        File whose suffix is inspected.

    Returns
    -------
    tuple of str or None
    """
    return EXTENSION_READERS.get(path.suffix.lower())


@registry.add(
    name="list_files",
    description=(
        "List data files in a directory so you can see what is available "
        "before loading anything.\n"
        "Returns each file with its size and the ChiSurf experiment type "
        "guessed from its extension. Use this whenever the user refers to "
        "'the files in <folder>' — never guess file names."
    ),
    parameters={
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "Directory to list. Relative paths resolve against the working directory.",
            },
            "pattern": {
                "type": "string",
                "description": "Glob pattern for the file names, e.g. '*.dat'. Default '*'.",
            },
            "recursive": {
                "type": "boolean",
                "description": "Also descend into sub-directories. Default false.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of files to return. Default 200.",
            },
        },
        "required": ["directory"],
    },
    safety=SAFETY_READ,
)
def list_files(
    context: AgentContext,
    directory: str,
    pattern: str = "*",
    recursive: bool = False,
    limit: int = 200,
) -> dict[str, Any]:
    """List candidate data files in *directory*."""
    root = context.resolve_path(directory)
    if not root.exists():
        raise ToolError(
            f"directory does not exist: {root}. "
            f"Paths are relative to the working directory — do not repeat it. "
            f"The {context.describe_working_directory()}"
        )
    if not root.is_dir():
        raise ToolError(f"not a directory: {root}")

    matches = root.rglob(pattern) if recursive else root.glob(pattern)
    files: list[dict[str, Any]] = []
    directories: list[str] = []
    for entry in sorted(matches):
        if entry.is_dir():
            directories.append(entry.name)
            continue
        if entry.name.startswith("."):
            continue
        if entry.suffix.lower() in _IGNORED_SUFFIXES:
            continue
        guess = guess_experiment(entry)
        files.append(
            {
                "path": str(entry),
                "name": entry.name,
                "size_kb": round(entry.stat().st_size / 1024.0, 1),
                "experiment": guess[0] if guess else None,
                "reader": guess[1] if guess else None,
            }
        )
        if len(files) >= int(limit):
            break

    result: dict[str, Any] = {
        "ok": True,
        "directory": str(root),
        "n_files": len(files),
        "files": files,
        "subdirectories": directories[:50],
    }
    if not files and directories and not recursive:
        # The common case of "the data is one level down": say so instead of
        # letting the model conclude the folder is empty.
        result["hint"] = (
            f"No file matched {pattern!r} directly in this directory, but it "
            f"has {len(directories)} sub-directories ({', '.join(directories[:10])}). "
            f"Call list_files again with recursive=true, or on one of them."
        )
    elif not files:
        result["hint"] = f"Nothing matched {pattern!r} here. Try pattern='*' to see every file."
    return result


@registry.add(
    name="list_experiments",
    description=(
        "List the ChiSurf experiment types with their file readers and their "
        "fitting models.\n"
        "Call this before create_fit so you use an exact model name — model "
        "names must match one of the names returned here."
    ),
    parameters={
        "type": "object",
        "properties": {
            "experiment": {
                "type": "string",
                "description": "Restrict the answer to one experiment, e.g. 'TCSPC'.",
            }
        },
    },
    safety=SAFETY_READ,
)
def list_experiments(
    context: AgentContext,
    experiment: str | None = None,
) -> dict[str, Any]:
    """Describe registered experiments, readers and models."""
    registry_description = context.ensure_experiments()
    if experiment:
        wanted = experiment.strip().lower()
        registry_description = {
            name: value for name, value in registry_description.items() if name.lower() == wanted
        }
        if not registry_description:
            raise ToolError(
                f"unknown experiment {experiment!r}; call list_experiments "
                f"without arguments to see the available ones"
            )
    return {"ok": True, "experiments": registry_description}


def _resolve_reader(
    context: AgentContext,
    path: pathlib.Path,
    experiment: str | None,
    reader: str | None,
) -> Any:
    """Return the reader to use for *path*.

    Parameters
    ----------
    context : AgentContext
        Execution context.
    path : pathlib.Path
        File to be loaded.
    experiment : str or None
        Experiment name given by the caller.
    reader : str or None
        Reader name given by the caller.

    Raises
    ------
    ToolError
        When no reader can be determined.
    """
    from chisurf.core.experiments.bootstrap import find_reader

    context.ensure_experiments()
    if experiment or reader:
        found = find_reader(experiment, reader)
        if found is None:
            raise ToolError(
                f"no reader {reader!r} for experiment {experiment!r}; "
                f"call list_experiments to see valid combinations"
            )
        return found

    guess = guess_experiment(path)
    if guess is None:
        raise ToolError(
            f"cannot tell which reader to use for '{path.name}' "
            f"(unknown extension '{path.suffix}'). Call list_experiments and "
            f"pass an explicit experiment and reader."
        )
    found = find_reader(*guess)
    if found is None:
        # The preferred reader is unavailable (e.g. a Qt-only reader in a
        # headless session); fall back to any reader of that experiment.
        found = find_reader(guess[0], None)
    if found is None:
        raise ToolError(
            f"experiment {guess[0]!r} has no usable reader in this session; "
            f"call list_experiments to see what is available"
        )
    return found


@registry.add(
    name="load_data",
    description=(
        "Load one or more data files into the ChiSurf session.\n"
        "Accepts explicit file paths and/or a directory (every matching file "
        "in it is loaded). The reader is chosen from the file extension "
        "unless you pass experiment/reader explicitly.\n"
        "Returns the index of every dataset that was loaded — those indices "
        "are what create_fit takes."
    ),
    parameters={
        "type": "object",
        "properties": {
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File paths to load. A directory entry loads its matching files.",
            },
            "directory": {
                "type": "string",
                "description": "Directory to load files from (alternative to 'paths').",
            },
            "pattern": {
                "type": "string",
                "description": "Glob used with 'directory' or a directory in 'paths'. Default '*'.",
            },
            "experiment": {
                "type": "string",
                "description": "Force an experiment type, e.g. 'TCSPC'. Default: guessed from the extension.",
            },
            "reader": {
                "type": "string",
                "description": "Force a reader name, e.g. 'TXT/CSV'. Default: guessed from the extension.",
            },
        },
    },
    safety=SAFETY_WRITE,
)
def load_data(
    context: AgentContext,
    paths: list[str] | None = None,
    directory: str | None = None,
    pattern: str = "*",
    experiment: str | None = None,
    reader: str | None = None,
) -> dict[str, Any]:
    """Load data files into the session and return the new dataset indices."""
    candidates: list[pathlib.Path] = []
    for raw in list(paths or []) + ([directory] if directory else []):
        resolved = context.resolve_path(raw)
        if resolved.is_dir():
            candidates.extend(
                sorted(
                    entry
                    for entry in resolved.glob(pattern)
                    if entry.is_file()
                    and not entry.name.startswith(".")
                    and entry.suffix.lower() not in _IGNORED_SUFFIXES
                )
            )
        elif resolved.exists():
            candidates.append(resolved)
        else:
            raise ToolError(
                f"path does not exist: {resolved}. Paths are relative to the "
                f"working directory — do not repeat it. "
                f"The {context.describe_working_directory()}. "
                f"Use list_files to see what is there."
            )

    if not candidates:
        raise ToolError(
            "no files to load — pass 'paths' or a 'directory' that contains "
            "matching files (check the 'pattern' argument)"
        )

    loaded: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for path in candidates:
        before = len(context.datasets)
        try:
            experiment_reader = _resolve_reader(context, path, experiment, reader)
            cs.core.actions.dispatch(
                name="dataset.add",
                payload={
                    "filename": str(path),
                    "experiment_reader": experiment_reader,
                },
            )
        except ToolError as error:
            failures.append({"file": path.name, "error": str(error)})
            continue
        except Exception as error:  # reader-level failure
            logger.debug("load_data failed for %s", path, exc_info=True)
            failures.append({"file": path.name, "error": f"{type(error).__name__}: {error}"})
            continue

        datasets = context.datasets
        if len(datasets) <= before:
            failures.append({"file": path.name, "error": "reader returned no dataset"})
            continue
        for index in range(before, len(datasets)):
            loaded.append(dataset_summary(datasets[index], index))

    if not loaded and failures:
        raise ToolError(
            "none of the files could be loaded: "
            + "; ".join(f"{f['file']}: {f['error']}" for f in failures[:5])
        )

    result: dict[str, Any] = {
        "ok": True,
        "n_loaded": len(loaded),
        "datasets": loaded,
        "dataset_indices": [entry["index"] for entry in loaded],
    }
    if failures:
        result["failures"] = failures
    irf_like = [entry["index"] for entry in loaded if _looks_like_irf_name(entry.get("name", ""))]
    if irf_like:
        # An IRF loaded alongside samples is a reference measurement, not
        # something to fit; saying so here stops the model from fitting it.
        result["likely_irf_datasets"] = irf_like
        result["hint"] = (
            f"Datasets {irf_like} look like instrument-response (IRF) "
            f"measurements, not samples. Do not fit them — attach one to a "
            f"decay fit with set_irf instead."
        )
    return result


def _looks_like_irf_name(name: str) -> bool:
    """Return whether a dataset name suggests an instrument-response file."""
    from chisurf.core.agent.tools.decay import IRF_NAME_HINTS

    lowered = str(name).lower()
    return any(hint in lowered for hint in IRF_NAME_HINTS)


@registry.add(
    name="list_datasets",
    description="List the datasets currently loaded in the ChiSurf session, with their indices.",
    parameters={"type": "object", "properties": {}},
    safety=SAFETY_READ,
)
def list_datasets(context: AgentContext) -> dict[str, Any]:
    """Return every loaded dataset."""
    datasets = context.datasets
    return {
        "ok": True,
        "n_datasets": len(datasets),
        "datasets": [dataset_summary(d, i) for i, d in enumerate(datasets)],
    }


@registry.add(
    name="get_curve",
    description=(
        "Return the numeric curve of a dataset, down-sampled.\n"
        "Use this only when you need to inspect the data itself (e.g. to "
        "judge a decay's shape or count rate); it is expensive in context."
    ),
    parameters={
        "type": "object",
        "properties": {
            "dataset": {
                "type": ["integer", "string"],
                "description": "Dataset index or name.",
            },
            "max_points": {
                "type": "integer",
                "description": "Maximum number of points to return. Default 64.",
            },
        },
        "required": ["dataset"],
    },
    safety=SAFETY_READ,
)
def get_curve(
    context: AgentContext,
    dataset: Any,
    max_points: int = 64,
) -> dict[str, Any]:
    """Return a down-sampled ``(x, y)`` view of a dataset."""
    import numpy as np

    obj, index = context.resolve_dataset(dataset)
    x = getattr(obj, "x", None)
    y = getattr(obj, "y", None)
    if y is None:
        raise ToolError(f"dataset {index} has no y values")
    y = np.asarray(y, dtype=float).ravel()
    x = np.arange(y.size, dtype=float) if x is None else np.asarray(x, dtype=float).ravel()
    step = max(1, int(y.size // max(1, int(max_points))))
    return {
        "ok": True,
        "dataset": index,
        "name": str(getattr(obj, "name", "")),
        "n_points": int(y.size),
        "step": step,
        "x": [round(float(v), 6) for v in x[::step]],
        "y": [round(float(v), 6) for v in y[::step]],
        "y_max": round(float(np.nanmax(y)), 3) if y.size else None,
        "y_sum": round(float(np.nansum(y)), 3) if y.size else None,
    }
