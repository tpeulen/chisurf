"""Detection workflows: a run described by a JSON document rather than a command.

A detection is a recipe — which detector, at what threshold, over which files,
written under which name — and a recipe that exists only as a command line is a
recipe that cannot be versioned, shared, reviewed or attached to a result. So
the same run can be written down:

.. code-block:: json

    {
      "workflow": "single_molecule",
      "settings": {"min_area": 4},
      "inputs": {"files": ["field_01.ptu", "field_02.ptu"]}
    }

The ``workflow`` names a **base** — one of the shipped documents in
``workflows/`` — and ``settings`` overrides only what differs from it, so a file
a person writes is short and says what is unusual about their sample rather than
restating every default. :data:`STANDARD` is the base when none is named, and it
is single-molecule segmentation: the watershed pipeline the molecule-wise MLE
has always used, which is what "a detection" means here unless someone says
otherwise.

Unknown keys are **refused**, in the document and in the settings alike. A
misspelled setting that is quietly ignored is the worst outcome available: the
run succeeds, the file records settings that were never applied, and the
difference shows up as a number nobody can explain.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = [
    "STANDARD",
    "WORKFLOW_VERSION",
    "builtin_workflow",
    "list_workflows",
    "load_workflow",
    "request_from_workflow",
    "workflow_from_request",
    "workflows_dir",
]

#: The document format's version. A reader that meets a higher number stops
#: rather than guessing which half of the document it still understands.
WORKFLOW_VERSION = 1

#: The base used when a document names none. Single-molecule segmentation is
#: the standard workflow: this is the tool's default answer to "detect".
STANDARD = "single_molecule"

#: Keys a workflow document may carry. Anything else is a mistake worth naming.
_DOCUMENT_KEYS = frozenset(
    {"workflow", "version", "description", "name", "settings", "inputs", "output"}
)
_INPUT_KEYS = frozenset({"files", "channels", "frame"})
_OUTPUT_KEYS = frozenset({"write", "out_dir"})


def workflows_dir() -> Path:
    """Return the directory holding the shipped workflow documents.

    Returns
    -------
    pathlib.Path
    """
    return Path(__file__).resolve().parent.parent / "workflows"


def list_workflows() -> list[str]:
    """Return the names of the shipped workflows, the standard one first.

    Returns
    -------
    list of str
    """
    names = sorted(p.stem for p in workflows_dir().glob("*.json"))
    if STANDARD in names:
        names.remove(STANDARD)
        names.insert(0, STANDARD)
    return names


def builtin_workflow(name: str = STANDARD) -> dict[str, Any]:
    """Return a shipped workflow document by name.

    Parameters
    ----------
    name : str, optional
        One of :func:`list_workflows`.

    Returns
    -------
    dict

    Raises
    ------
    FileNotFoundError
        If there is no such workflow — listing the ones there are, because a
        name that does not exist is usually a name that nearly does.
    """
    path = workflows_dir() / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"no workflow named {name!r}; the shipped ones are: "
            + ", ".join(list_workflows())
        )
    return json.loads(path.read_text())


def load_workflow(source) -> dict[str, Any]:
    """Return a fully-resolved workflow document.

    Parameters
    ----------
    source : str, pathlib.Path or dict
        A shipped workflow's name, a path to a JSON file, or a document
        already in memory.

    Returns
    -------
    dict
        The named base with the caller's overrides merged over it, validated.

    Raises
    ------
    ValueError
        On an unknown key, an unknown setting, or a version this reader does
        not implement.
    FileNotFoundError
        If a named workflow or a path does not exist.
    """
    if isinstance(source, dict):
        document = dict(source)
    else:
        text = str(source)
        path = Path(text)
        if path.suffix.lower() == ".json" or path.exists():
            if not path.exists():
                raise FileNotFoundError(f"no such workflow file: {path}")
            document = json.loads(path.read_text())
        else:
            document = builtin_workflow(text)

    _check_keys(document, _DOCUMENT_KEYS, "workflow document")
    version = int(document.get("version", WORKFLOW_VERSION))
    if version > WORKFLOW_VERSION:
        raise ValueError(
            f"workflow document is version {version}; this ChiSurf reads "
            f"version {WORKFLOW_VERSION}. Refusing rather than applying the "
            "half of it that still parses."
        )

    base_name = document.get("workflow", STANDARD)
    resolved: dict[str, Any]
    if isinstance(source, dict) or Path(str(source)).suffix.lower() == ".json":
        # A document naming a base inherits it; the base names itself, so this
        # terminates without a cycle check being interesting.
        base = builtin_workflow(base_name)
        resolved = dict(base)
        resolved["settings"] = {**base.get("settings", {}), **(document.get("settings") or {})}
        for key in ("name", "description", "inputs", "output"):
            if key in document:
                resolved[key] = document[key]
        resolved["workflow"] = base_name
    else:
        resolved = document

    _check_keys(resolved.get("inputs") or {}, _INPUT_KEYS, "workflow inputs")
    _check_keys(resolved.get("output") or {}, _OUTPUT_KEYS, "workflow output")
    _check_settings(resolved.get("settings") or {})
    resolved.setdefault("version", WORKFLOW_VERSION)
    return resolved


def request_from_workflow(document, *, files=None, out_dir: str = ""):
    """Build a detection request from a workflow document.

    Parameters
    ----------
    document : str, pathlib.Path or dict
        Anything :func:`load_workflow` accepts.
    files : sequence of str, optional
        Files to detect in, overriding the document's own. A workflow that
        carries no files is the normal case — a recipe is about *how*, and the
        caller supplies the *what*.
    out_dir : str, optional
        Overrides the document's output directory.

    Returns
    -------
    SpotFinderRequest
    """
    from ..api.models import SpotFinderRequest
    from .spots import SpotFinderSettings

    resolved = load_workflow(document)
    inputs = resolved.get("inputs") or {}
    output = resolved.get("output") or {}

    settings = SpotFinderSettings(**(resolved.get("settings") or {}))
    settings.workflow = resolved.get("workflow", STANDARD)

    return SpotFinderRequest(
        files=[str(f) for f in (files if files is not None else inputs.get("files") or [])],
        name=resolved.get("name", "spots"),
        channels=list(inputs["channels"]) if inputs.get("channels") else None,
        frame=int(inputs.get("frame", -1)),
        settings=settings,
        write=bool(output.get("write", True)),
        out_dir=out_dir or str(output.get("out_dir", "")),
    )


def workflow_from_request(request, *, description: str = "") -> dict[str, Any]:
    """Return the workflow document that would reproduce *request*.

    The other direction, and the one that makes a tuned run reusable: settings
    arrived at by hand in a GUI or on a command line become a document that can
    be committed beside the data.

    Parameters
    ----------
    request : SpotFinderRequest
        The run to write down — settings, inputs and where the results go.
    description : str, optional
        Prose for the document, for whoever opens it next.

    Returns
    -------
    dict
    """
    import dataclasses

    settings = dataclasses.asdict(request.settings)
    workflow = settings.pop("workflow", STANDARD)
    roi = settings.get("roi")
    if roi is not None and not isinstance(roi, (dict, list, str, int, float, bool)):
        # A region is a live object here and a serialised one in a document.
        settings["roi"] = roi.to_dict() if hasattr(roi, "to_dict") else str(roi)

    document: dict[str, Any] = {
        "workflow": workflow,
        "version": WORKFLOW_VERSION,
        "name": request.name,
        "settings": settings,
        "inputs": {"files": list(request.files), "frame": request.frame},
        "output": {"write": request.write, "out_dir": request.out_dir},
    }
    if request.channels:
        document["inputs"]["channels"] = list(request.channels)
    if description:
        document["description"] = description
    return document


def _check_keys(mapping, allowed, what: str) -> None:
    """Raise on any key outside *allowed*, naming the nearest legal one."""
    unknown = sorted(set(mapping) - set(allowed))
    if unknown:
        raise ValueError(
            f"unknown {what} key(s): {', '.join(unknown)}. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )


def _check_settings(settings) -> None:
    """Raise on a setting the detector does not have.

    The whole point of refusing: a document that carries ``min_size`` where the
    setting is ``min_area`` would otherwise run happily at the default and
    record a parameter that never took effect.
    """
    import dataclasses

    from .spots import SpotFinderSettings

    allowed = {f.name for f in dataclasses.fields(SpotFinderSettings)}
    _check_keys(settings, allowed, "detection setting")
