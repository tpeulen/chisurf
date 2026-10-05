from __future__ import annotations

import base64
import datetime
import json
import pathlib
import zlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Union

from .archive import ProjectArchive
from .pto import PROJECT_SUFFIX

PathLike = Union[str, pathlib.Path]
_RESOURCE_CONTEXT_ALIAS = "urn:chisurf:project:resource-context"


class ResourceContext:
    """Owned immutable attachment bytes and their exact named source aliases.

    Archive entries remain outside the scientific DTO. Source labels are metadata,
    never permission to read paths on restoration or on a server.
    """

    def __init__(
        self, entries: Mapping[str, bytes] | None = None, sources: Mapping[str, bytes] | None = None
    ):
        owned = self._validate_entries(entries or {})
        aliases = dict(sources or {})
        if _RESOURCE_CONTEXT_ALIAS in aliases:
            raise ValueError("Reserved resource context alias")
        if any(
            not isinstance(k, str) or not k or not isinstance(v, bytes) for k, v in aliases.items()
        ):
            raise TypeError("Resource aliases must map nonempty labels to bytes")
        if "mmfdb_export.json" in owned:
            export = json.loads(owned["mmfdb_export.json"])
            dependencies = export.get("dependencies", {})
            objects = {
                obj["object_uuid"]: base64.b64decode(obj["data_base64"], validate=True)
                for obj in dependencies.get("objects", [])
            }
            carried = None
            for artifact in dependencies.get("artifacts", []):
                if artifact.get("artifact_kind") == "raw_measurement":
                    label = artifact["file_path"]
                    content = objects[artifact["object_uuid"]]
                    if label == _RESOURCE_CONTEXT_ALIAS:
                        carried = self._decode_database_descriptor(content)
                        continue
                    if label in aliases and aliases[label] != content:
                        raise ValueError(f"Conflicting resource alias {label!r}")
                    aliases[label] = content
            if carried is not None:
                # Preserve the originally supplied native entries, rather than
                # recursively embedding every subsequently generated DB export.
                owned = self._validate_entries(carried["entries"])
                for label, content in carried["sources"].items():
                    if label in aliases and aliases[label] != content:
                        raise ValueError(f"Conflicting resource alias {label!r}")
                    aliases[label] = content
        if "resources.json" in owned:
            encoded = json.loads(owned["resources.json"])
            if not isinstance(encoded, dict) or any(
                not isinstance(k, str) or not k or not isinstance(v, str)
                for k, v in encoded.items()
            ):
                raise ValueError("Invalid portable resource byte codec")
            for label, value in encoded.items():
                content = base64.b64decode(value, validate=True)
                if label in aliases and aliases[label] != content:
                    raise ValueError(f"Conflicting resource alias {label!r}")
                aliases[label] = content
        if _RESOURCE_CONTEXT_ALIAS in aliases or any(
            not isinstance(k, str) or not k or not isinstance(v, bytes) for k, v in aliases.items()
        ):
            raise ValueError("Invalid retained resource aliases")
        self.entries = MappingProxyType(owned)
        self.sources = MappingProxyType(aliases)

    @staticmethod
    def _validate_entries(entries: Mapping[str, bytes]) -> dict[str, bytes]:
        """Validate native entry names and exact byte values without extraction."""
        owned = {}
        for name, value in entries.items():
            if (
                not isinstance(name, str)
                or not name
                or name.startswith("/")
                or "\\" in name
                or ".." in pathlib.PurePosixPath(name).parts
                or name == "project.json"
            ):
                raise ValueError(f"Unsafe resource entry {name!r}")
            if not isinstance(value, bytes):
                raise TypeError("Resource content must be bytes")
            owned[name] = value
        return owned

    def __deepcopy__(self, memo: dict) -> ResourceContext:
        """Retain immutable bytes by identity when snapshots copy owned history."""
        return self

    def write_to_archive(self, archive: Any) -> None:
        """Write retained entries and explicit byte aliases without path access."""
        for name, content in self.entries.items():
            if name != "resources.json":
                archive.write_bytes(name, content)
        if self.sources:
            archive.write_text("resources.json", json.dumps(self.encoded_sources(), sort_keys=True))

    def encoded_sources(self) -> dict[str, str]:
        """Encode named source bytes for authenticated JSON transport."""
        return {name: base64.b64encode(data).decode("ascii") for name, data in self.sources.items()}

    def to_transport_dict(self) -> dict[str, dict[str, str]]:
        """Encode only named bytes for the public owner transaction transport."""
        return {
            "entries": {
                name: base64.b64encode(data).decode("ascii") for name, data in self.entries.items()
            },
            "sources": self.encoded_sources(),
        }

    @classmethod
    def from_transport_dict(cls, payload: Any) -> ResourceContext:
        """Validate a resource-only byte codec without importing or opening paths."""
        return cls(**cls._decode_transport_dict(payload))

    @staticmethod
    def _decode_transport_dict(payload: Any) -> dict[str, dict[str, bytes]]:
        """Decode a finite named byte descriptor, without recursively constructing it."""
        if not isinstance(payload, dict) or set(payload) != {"entries", "sources"}:
            raise ValueError("Invalid resource transport codec")
        decoded = {}
        for kind, values in payload.items():
            if not isinstance(values, dict) or any(
                not isinstance(k, str) or not k or not isinstance(v, str) for k, v in values.items()
            ):
                raise ValueError("Invalid resource transport mapping")
            decoded[kind] = {
                name: base64.b64decode(value, validate=True) for name, value in values.items()
            }
        return decoded

    def database_bundle(self) -> dict[str, str]:
        """Carry native entries and source aliases through existing resource_bundle."""
        bundle = self.encoded_sources()
        if self.entries:
            # Aliases already travel separately. Do not duplicate their bytes
            # inside the native-entry descriptor or recursively grow exports.
            state = self.to_transport_dict()
            state["sources"] = {}
            decoded = json.dumps(state, sort_keys=True).encode("utf-8")
            descriptor = json.dumps(
                {
                    "encoding": "zlib-base64",
                    "decoded_size": len(decoded),
                    "data": base64.b64encode(zlib.compress(decoded)).decode("ascii"),
                }
            ).encode("utf-8")
            bundle[_RESOURCE_CONTEXT_ALIAS] = base64.b64encode(descriptor).decode("ascii")
        return bundle

    @classmethod
    def _decode_database_descriptor(cls, content: bytes) -> dict[str, dict[str, bytes]]:
        """Decode only the bounded lossless native-entry byte descriptor."""
        descriptor = json.loads(content)
        if (
            not isinstance(descriptor, dict)
            or set(descriptor) != {"encoding", "decoded_size", "data"}
            or descriptor["encoding"] != "zlib-base64"
            or type(descriptor["decoded_size"]) is not int
            or not 0 <= descriptor["decoded_size"] <= 64 * 1024 * 1024
            or not isinstance(descriptor["data"], str)
        ):
            raise ValueError("Invalid database resource byte descriptor")
        decompressor = zlib.decompressobj()
        decoded = decompressor.decompress(
            base64.b64decode(descriptor["data"], validate=True), descriptor["decoded_size"] + 1
        )
        if (
            len(decoded) != descriptor["decoded_size"]
            or not decompressor.eof
            or decompressor.unused_data
            or decompressor.unconsumed_tail
        ):
            raise ValueError("Invalid database resource byte length")
        return cls._decode_transport_dict(json.loads(decoded))


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
    project_format_version: int = 5
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
    resources: ResourceContext = field(default_factory=ResourceContext, repr=False, compare=False)

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
        """Reconstruct a :class:`Project` from a dictionary. V5 format only."""
        if not isinstance(data, dict):
            raise ValueError("Project payload must be a mapping")
        version = int(data.get("project_format_version", 0))
        if version != 5:
            raise ValueError(
                f"Unsupported project format version: {version}; this build requires v5"
            )

        meta = data.get("meta", {})
        if not isinstance(meta, dict):
            raise ValueError("Project section 'meta' must be a mapping")

        expected_types = {
            "datasets": dict,
            "experiments": dict,
            "fits": list,
            "ui": dict,
            "extra": dict,
            "dependency_edges": list,
            "parameters": dict,
        }
        for section, expected in expected_types.items():
            if section in data and not isinstance(data[section], expected):
                raise ValueError(f"Project section {section!r} must be a {expected.__name__}")

        # Extract explicit metadata keys not part of the root
        core_meta_keys = {"name", "description", "chisurf_version", "created"}
        metadata = {k: v for k, v in meta.items() if k not in core_meta_keys}

        return cls(
            name=meta.get("name", "untitled"),
            description=meta.get("description", ""),
            chisurf_version=meta.get("chisurf_version"),
            project_format_version=5,
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
        self.resources.write_to_archive(archive)

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
        archive = ProjectArchive()
        self.save_to_archive(archive)
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
        from .pto import _validate_project_payload

        data = _validate_project_payload(data)
        archive.close()
        project = cls.from_dict(data)
        project.resources = ResourceContext(
            {
                name: archive.read_bytes(name)
                for name in archive.list_entries()
                if name != "project.json"
            }
        )
        project._archive_path = project_path
        return project


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
