from __future__ import annotations

import datetime
import json
import pathlib
import tempfile
from dataclasses import dataclass, field
from typing import Any, Union

from .archive import ProjectArchive
from .pto import PROJECT_SUFFIX, ProjectPtoError

PathLike = Union[str, pathlib.Path]


@dataclass
class Project:
    """Minimal, GUI-independent representation of a ChiSurf project.

    This class persists one ``.cs.pto`` project through ptolib. The portable
    JSON project state and optional BFF graph session are distinct typed PTO
    objects so a generic reader can inspect the file without ZIP conventions.
    """

    name: str = "untitled"
    description: str = ""
    chisurf_version: str | None = None
    project_format_version: int = 4
    # Creation timestamp (ISO 8601). Mainly for user information.
    created: str = field(default_factory=lambda: datetime.datetime.now().isoformat())

    # Core state sections keyed by UID or strict lists:
    datasets: dict[str, dict[str, Any]] = field(default_factory=dict)
    experiments: dict[str, dict[str, Any]] = field(default_factory=dict)
    fits: list[dict[str, Any]] = field(default_factory=list)
    ui_state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    dependency_edges: list[dict[str, Any]] = field(default_factory=list)
    parameters: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert this project into a deterministic JSON-serializable dictionary."""
        sorted_datasets = {k: self.datasets[k] for k in sorted(self.datasets.keys())}
        sorted_experiments = {k: self.experiments[k] for k in sorted(self.experiments.keys())}

        return {
            "project_format_version": self.project_format_version,
            "meta": {
                "name": self.name,
                "description": self.description,
                "chisurf_version": self.chisurf_version,
                "created": self.created,
                **self.metadata,
            },
            "datasets": sorted_datasets,
            "experiments": sorted_experiments,
            "fits": self.fits,
            "ui": self.ui_state,
            "extra": self.extra,
            "dependency_edges": self.dependency_edges,
            "parameters": self.parameters,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        """Reconstruct a :class:`Project` from a dictionary. V4 format only."""
        version = int(data.get("project_format_version", 1))
        if version < 4:
            raise ValueError(
                f"Unsupported project format version: {version}. "
                "This build requires v4 (UID-keyed). v3 and earlier projects are not supported."
            )

        meta = data.get("meta", {})

        # Extract explicit metadata keys not part of the root
        core_meta_keys = {"name", "description", "chisurf_version", "created"}
        metadata = {k: v for k, v in meta.items() if k not in core_meta_keys}

        return cls(
            name=meta.get("name", "untitled"),
            description=meta.get("description", ""),
            chisurf_version=meta.get("chisurf_version"),
            project_format_version=4,
            created=meta.get("created") or datetime.datetime.now().isoformat(),
            datasets=data.get("datasets") or {},
            experiments=data.get("experiments") or {},
            fits=data.get("fits") or [],
            ui_state=data.get("ui") or {},
            metadata=metadata,
            extra=data.get("extra") or {},
            dependency_edges=data.get("dependency_edges") or [],
            parameters=data.get("parameters") or {},
        )

    def get_dataset(self, uid: str) -> dict[str, Any] | None:
        """Return a dataset payload by UID."""
        return self.datasets.get(uid)

    def get_fit(self, uid: str) -> dict[str, Any] | None:
        """Return a fit payload by UID."""
        for fit in self.fits:
            if fit.get("uid") == uid:
                return fit
        return None

    def list_dataset_uids(self) -> list[str]:
        """Return sorted dataset UIDs."""
        return sorted(list(self.datasets.keys()))

    def list_fit_uids(self) -> list[str]:
        """Return sorted fit UIDs."""
        uids = [fit.get("uid") for fit in self.fits if fit.get("uid")]
        return sorted(uids)

    def save_to_archive(self, archive) -> None:
        """Add the portable project record to an assembled PTO project.

        Macro/server callers may add history, BFF state and embedded data to
        the same container before it is published.  The method keeps that
        assembly path aligned with :meth:`save` without reintroducing ZIP.
        """
        archive.write_text("project.json", json.dumps(self.to_dict(), indent=2, sort_keys=True))

    def save(self, target_path: PathLike) -> pathlib.Path:
        """Save this project as a validated ``.cs.pto`` container.

        Parameters
        ----------
        target_path : str or pathlib.Path
            Destination archive path. If a directory is provided, the project is
            saved as ``project.cs.pto`` inside that directory.

        Returns
        -------
        pathlib.Path
        Path to the saved ``.cs.pto`` project.
        """
        project_path = _project_output_path(target_path)
        session_bytes = None
        try:
            import IMP.bff as bff

            with tempfile.TemporaryDirectory() as tmpdir:
                session_path = pathlib.Path(tmpdir) / "session.jsonl"
                bff.get_session().save(str(session_path))
                session_bytes = session_path.read_bytes()
        except ImportError:
            # A headless portable project remains useful without the optional
            # native graph backend. A project that needs it will say so via its
            # own records when opened.
            pass
        archive = ProjectArchive()
        self.save_to_archive(archive)
        if session_bytes is not None:
            archive.write_bytes("session.jsonl", session_bytes)
        return archive.save(project_path)

    @classmethod
    def load(cls, target_path: PathLike) -> Project:
        """Load a project from a validated ``.cs.pto`` container.

        Parameters
        ----------
        target_path : str or pathlib.Path
            Project path, or a directory containing ``project.cs.pto``.

        Returns
        -------
        Project
            Loaded project instance.
        """
        project_path = _project_input_path(target_path)
        archive = ProjectArchive.open(project_path)
        data = json.loads(archive.read_text("project.json"))
        session_bytes = (
            archive.read_bytes("session.jsonl") if archive.has_entry("session.jsonl") else None
        )
        archive.close()
        project = cls.from_dict(data)
        project._archive_path = project_path

        if session_bytes is not None:
            try:
                import IMP.bff as bff

                with tempfile.TemporaryDirectory() as tmpdir:
                    session_path = pathlib.Path(tmpdir) / "session.jsonl"
                    session_path.write_bytes(session_bytes)
                    _restore_bff_session(bff, session_path)
            except ImportError as exc:
                raise ProjectPtoError(
                    "This project contains a BFF graph session but IMP.bff is unavailable"
                ) from exc

        return project


def _restore_bff_session(bff, session_path) -> bool:
    """Load a saved node graph into the process-level bff session.

    ``Session.load`` is a *staticmethod* here too: it builds and returns a
    new session. Calling it and letting the result go would restore the
    graph into an object that was immediately discarded, so opening a
    project silently brought back no nodes at all.

    The restored nodes -- and the free ports, which is what chisurf's fit
    parameters are -- are moved into the existing ``bff.get_session()``
    instead of rebinding anything, so references held elsewhere keep
    pointing at the live session. The archive entry is unchanged: the same
    ``session.jsonl``, chinet's format, which bff's Session reads and
    writes field for field, so archives written by chinet-era chisurf open
    as they are.

    Parameters
    ----------
    bff : module
        The imported ``IMP.bff`` module.
    session_path : str or pathlib.Path
        The extracted ``session.jsonl``.

    Returns
    -------
    bool
        Whether a session was restored.
    """
    restored = bff.GraphSession.load(str(session_path))
    if restored is None:
        return False
    session = bff.get_session()
    session.clear()
    for name, node in restored.get_nodes().items():
        session.add_node(name, node)
    for port in restored.get_ports():
        session.add_port(port)
    return True


def save_project(project: Project, target_path: PathLike) -> pathlib.Path:
    """Convenience wrapper to save a :class:`Project`."""
    return project.save(target_path)


def load_project(target_path: PathLike) -> Project:
    """Convenience wrapper to load a :class:`Project` from a ``.cs.pto`` project."""
    return Project.load(target_path)


def _project_output_path(target_path: PathLike) -> pathlib.Path:
    path = pathlib.Path(target_path)
    if str(path).lower().endswith(PROJECT_SUFFIX):
        return path
    if path.exists() and path.is_dir():
        return path / f"project{PROJECT_SUFFIX}"
    if path.suffix:
        return pathlib.Path(f"{path}{PROJECT_SUFFIX}")
    return pathlib.Path(f"{path}{PROJECT_SUFFIX}")


def _project_input_path(target_path: PathLike) -> pathlib.Path:
    path = pathlib.Path(target_path)
    if str(path).lower().endswith(PROJECT_SUFFIX):
        return path
    if path.is_dir():
        return path / f"project{PROJECT_SUFFIX}"
    return pathlib.Path(f"{path}{PROJECT_SUFFIX}")
