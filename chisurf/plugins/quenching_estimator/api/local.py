"""QuEst's facade: the verbs, resolved to a local or a remote backend.

>>> from quest import api
>>> project = api.template(with_fret=False)
>>> result = api.simulate(project, pdb_path="tests/148l.pdb")
>>> result.donor_counts.shape == result.time.shape
True

# One registry behind every surface

This was a **re-export shim** until 2026-07-28 (`LAY-04`): it forwarded names
from `quest.core` and had no notion of where a call runs, so the web backend
reached past it into `quest.core` directly and a host had no single thing to
drive. The verbs below go through a *client* -- `InProcessClient` by default,
a remote one when :func:`use_client` is given another -- so every surface
exercises the same registry, the same validation and the same error codes.

# The results are native, not JSON

`simulate` hands back a `DecaySimulationResult` with its numpy arrays intact.
Serialization happens at a **transport** (`quest.rpc.contract.to_payload`),
not in a handler, because `OBJ-02` made a fitting loop QuEst's primary consumer
and converting every decay channel to a Python list per iteration is a tax it
would pay forever.

The trade: payload shape depends on the transport. `tests/test_contract.py`
round-trips each method's native result through `to_payload` and validates it
against the manifest schema, so the two cannot drift quietly.

# The domain is still importable

The classes and functions re-exported below stay: a notebook that wants
`build_donor_from_project` should have it, and pretending otherwise would just
send people to `quest.core` again. The difference is that the *verbs* are now
the supported way in.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional, Tuple

import numpy as np

# Re-export the headless backend so downstream imports stay stable.
from chisurf.plugins.quenching_estimator.core import (
    DecaySimulationResult,
    build_donor_from_project,
    load_project,
    simulate_project,
    top_quenchers,
)
from chisurf.plugins.quenching_estimator.core.fps_json import (
    load_fps_json,
    normalize_to_fps_positions,
    run_fps_scan,
)
from chisurf.plugins.quenching_estimator.core.project import (
    ProjectValidationError,
    template_project,
    validate_project,
)
from chisurf.plugins.quenching_estimator.core.structure import (
    download_pdb_id,
    is_pdb_id,
    resolve_structure_path,
)

#: The client every verb goes through. Swapped by :func:`use_client`.
_CLIENT = None


def client():
    """The active client, creating the default in-process one on first use.

    Lazy because building it registers twelve handlers, and `import quest.api`
    happens in places that never make a call.
    """

    global _CLIENT
    if _CLIENT is None:
        from chisurf.plugins.quenching_estimator.rpc import local_client

        _CLIENT = local_client()
    return _CLIENT


def use_client(new_client) -> None:
    """Point the verbs at *new_client* -- a remote transport, or a test double.

    This is the local/remote resolution `LAY-04` asked for. The call sites do
    not change; only what is behind them does.
    """

    global _CLIENT
    _CLIENT = new_client


def describe() -> dict:
    """The contract: methods, schemas, error codes, serialization boundary."""

    return client().result("quest.contract.describe")


def template(*, with_fret: bool = True) -> MutableMapping[str, Any]:
    """A minimal valid project, ready to edit."""

    return client().result("quest.template", {"with_fret": bool(with_fret)})["project"]


def validate(project: Mapping[str, Any], *, pdb_path: Optional[str] = None) -> None:
    """Raise `RemoteError` if *project* is malformed.

    The failure carries `error_code == "invalid_project"`, so a caller can tell
    a bad document from a failed simulation without reading the message.
    """

    client().result(
        "quest.validate",
        {"project": dict(project), "pdb_path": None if pdb_path is None else str(pdb_path)},
    )


def simulate(
    project: Mapping[str, Any],
    *,
    pdb_path: Optional[Path | str] = None,
    nbins: Optional[int] = None,
    tac_range: tuple[float, float] = (0.0, 50.0),
    project_dir: Optional[Path | str] = None,
    save_outputs: bool = False,
):
    """Run one simulation. Returns the **native** result object."""

    return client().result(
        "quest.simulate",
        {
            "project": dict(project),
            "pdb_path": None if pdb_path is None else str(pdb_path),
            "nbins": nbins,
            "tac_range": tuple(tac_range),
            "project_dir": None if project_dir is None else str(project_dir),
            "save_outputs": bool(save_outputs),
        },
    )


def scan(
    project: Mapping[str, Any],
    positions: Mapping[str, Mapping[str, Any]],
    *,
    pdb_path: Optional[Path | str] = None,
    nbins: Optional[int] = None,
    tac_range: tuple[float, float] = (0.0, 50.0),
    project_dir: Optional[Path | str] = None,
) -> dict:
    """Simulate a set of labelling sites, one record each."""

    return client().result(
        "quest.scan",
        {
            "project": dict(project),
            "positions": dict(positions),
            "pdb_path": None if pdb_path is None else str(pdb_path),
            "nbins": nbins,
            "tac_range": tuple(tac_range),
            "project_dir": None if project_dir is None else str(project_dir),
        },
    )["results"]


def parameter_catalog(locale: Optional[str] = None) -> dict:
    """Parameter labels, units and help, optionally translated."""

    return client().result("quest.parameter_catalog", {"locale": locale})


def dyes() -> dict:
    """The dye presets."""

    return client().result("quest.dyes.list")


def structure_metadata(pdb_path: Path | str) -> dict:
    """Chains, residues and atoms of a structure file."""

    return client().result("quest.structure.metadata", {"pdb_path": str(pdb_path)})


__all__ = [
    # -- the verbs ------------------------------------------------------
    "client",
    "use_client",
    "describe",
    "template",
    "validate",
    "simulate",
    "scan",
    "parameter_catalog",
    "dyes",
    "structure_metadata",
    # -- the domain, still importable -----------------------------------
    "DecaySimulationResult",
    "load_project",
    "simulate_project",
    "build_donor_from_project",
    "top_quenchers",
    "ProjectValidationError",
    "template_project",
    "validate_project",
    "download_pdb_id",
    "is_pdb_id",
    "resolve_structure_path",
    "load_fps_json",
    "normalize_to_fps_positions",
    "run_fps_scan",
]
