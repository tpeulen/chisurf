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
from .pto import PROJECT_SUFFIX, SESSION_FILENAME

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
    #: The folder the project was opened from: linked datasets resolve against it (not saved).
    source_dir: pathlib.Path | None = field(default=None, repr=False, compare=False)
    #: The ``.cs.pto`` this project was opened from or last saved to (embedded data lives there).
    source_path: pathlib.Path | None = field(default=None, repr=False, compare=False)

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
        uids = [str(fit["uid"]) for fit in self.fits if fit.get("uid")]
        return sorted(uids)

    def relativize_links(self, project_dir: PathLike) -> None:
        """Record each linked dataset's file relative to *project_dir*, where the project is saved.

        A project moved together with its measurements then finds them again
        (:mod:`chisurf.core.project.links`). No file is read or hashed here.
        """
        from .links import relativize

        for record in self.datasets.values():
            if isinstance(record, dict) and record.get("kind") == "linked":
                if isinstance(record.get("link"), dict):
                    record["link"] = relativize(record["link"], project_dir)

    def data_files(self, project_path: PathLike) -> list:
        """The linked and embedded data files this project's container carries when saved to
        *project_path* (:class:`chisurf.core.project.pto.ProjectFile`).

        Names each linked dataset's object (``link["object"]``, stable across saves) and records it
        in the dataset record, so ``project.cs.pto/<object>`` addresses it. An embedded dataset's
        bytes are streamed from where they are now: its current address (the file it was embedded
        from, or the previous save of the project), else wherever its link resolves.
        """
        from .links import is_embedded, object_tags, resolve
        from .pto import ProjectFile, ProjectPtoError

        project_dir = pathlib.Path(project_path).parent
        taken: set[str] = set()
        out: list = []
        for record in self.datasets.values():
            if not isinstance(record, dict) or record.get("kind") != "linked":
                continue
            link = record.get("link")
            if not isinstance(link, dict):
                continue
            name = _object_name(link, record, taken)
            link["object"] = name
            kind, encoding = _object_kind(record, link)
            tags = tuple(object_tags(link, project_dir))
            if not is_embedded(link):
                out.append(ProjectFile(name, kind, encoding, tags))
                continue
            source = _embedded_source(record, link, project_dir) or _saved_object(
                pathlib.Path(project_path), name, int(link.get("size", -1))
            )
            if source is None:
                raise ProjectPtoError(
                    f"The data of {record.get('name') or name!r} is embedded but not available: "
                    "neither its last save nor its original file was found"
                )
            out.append(ProjectFile(name, kind, encoding, tags, source, int(link.get("size", 0))))
            for companion in link.get("companions") or ():
                comp_name = (
                    pathlib.PurePosixPath(name).stem
                    + pathlib.Path(str(companion.get("name", ""))).suffix
                )
                taken.add(comp_name)
                out.append(
                    ProjectFile(
                        comp_name,
                        "raw_measurement",
                        "setup",
                        (),
                        _companion_source(source, str(companion.get("name", "")), comp_name),
                        int(companion.get("size", 0)),
                        sidecar_of=name,
                    )
                )
        return out

    def save_to_archive(self, archive, graph_session_bytes: bytes | None = None) -> None:
        """Add the portable project record to an assembled PTO project.

        Macro/server callers may add history, BFF state and embedded data to
        the same container before it is published.  The method keeps that
        assembly path aligned with :meth:`save` without reintroducing ZIP.

        The live bff graph session travels as the typed ``session.jsonl``
        entry: captured from the running session unless *graph_session_bytes*
        is given, and left out entirely when there is nothing to persist (no
        IMP.bff, or an empty session).
        """
        if graph_session_bytes is None:
            from .graph import capture_graph_session

            graph_session_bytes = capture_graph_session()
        archive.write_text("project.json", json.dumps(self.to_dict(), indent=2, sort_keys=True))
        self.resources.write_to_archive(archive)
        if graph_session_bytes is not None:
            archive.write_bytes(SESSION_FILENAME, graph_session_bytes)

    def save(
        self, target_path: PathLike, *, graph_session_bytes: bytes | None = None
    ) -> pathlib.Path:
        """Save this project as a validated ``.cs.pto`` container.

        Parameters
        ----------
        target_path : str or pathlib.Path
            Destination archive path. If a directory is provided, the project is
            saved as ``project.cs.pto`` inside that directory.
        graph_session_bytes : bytes, optional
            Pre-captured bff graph session; captured from the live session when
            omitted (see :meth:`save_to_archive`).

        Returns
        -------
        pathlib.Path
        Path to the saved ``.cs.pto`` project.
        """
        project_path = _project_output_path(target_path)
        self.relativize_links(project_path.parent)
        files = self.data_files(project_path)  # names the objects before the records are written
        archive = ProjectArchive()
        self.save_to_archive(archive, graph_session_bytes)
        saved = archive.save(project_path, files=files)
        self.source_path, self.source_dir = saved, saved.parent
        adopt_saved_links(self, saved)
        return saved

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
        # Linked datasets resolve against the folder the project was opened from; embedded ones are
        # read from the file itself.
        project.source_dir = project_path.parent
        project.source_path = project_path
        project.resources = ResourceContext(
            {
                name: archive.read_bytes(name)
                for name in archive.list_entries()
                if name != "project.json" and name != SESSION_FILENAME
            }
        )
        if archive.has_entry(SESSION_FILENAME):
            # The live graph travels with the file again (owner 2026-10-24):
            # keep the bytes on the project and install them as the session.
            project.graph_session_bytes = archive.read_bytes(SESSION_FILENAME)
            from .graph import restore_graph_session

            restore_graph_session(project.graph_session_bytes)
        return project


def _object_name(link: dict, record: dict, taken: set[str]) -> str:
    """The container object name of a linked dataset: kept across saves, else its file's name,
    made unique with the dataset's uid."""
    name = str(link.get("object") or "")
    if not name:
        container = pathlib.Path(str(link.get("container", "")))
        member = str(link.get("member") or "")
        name = pathlib.PurePosixPath(member).name if member else container.name
        name = name or str(record.get("uid", "data"))
    if name in taken:
        stem, suffix = pathlib.PurePosixPath(name).stem, pathlib.PurePosixPath(name).suffix
        name = f"{stem}~{str(record.get('uid', ''))[:8]}{suffix}"
    taken.add(name)
    return name


def _object_kind(record: dict, link: dict) -> tuple[str, str]:
    """The ptolib kind and encoding of a linked dataset's object (a reader picks the decoder from
    the encoding)."""
    from chisurf.core.fio.pto import _encoding_for

    container = pathlib.Path(str(link.get("container", "")))
    if container.suffix.lower() == ".pto":
        return "pto_container", "pto"
    data_kind = str(record.get("data_kind", ""))
    if data_kind == "photons":
        return "tttr_photon_stream", _encoding_for(container)
    if data_kind == "image":
        return "image_data", container.suffix.lstrip(".").lower() or "unknown"
    return "raw_measurement", container.suffix.lstrip(".").lower() or "unknown"


def _embedded_source(record: dict, link: dict, project_dir: pathlib.Path) -> str | None:
    """Where an embedded dataset's bytes are now (a file path or a container object address)."""
    from chisurf.core.fio.address import split_address

    from .links import resolve

    address = str(record.get("address", ""))
    if address:
        container, member = split_address(address)
        if container is not None:
            if not member:
                return str(container)  # the file it was embedded from
            if str(container).endswith(PROJECT_SUFFIX):
                return address  # the previous save of the project: its object
            # a member of a measurement container: the link's target is that container (below)
    resolution = resolve({k: v for k, v in link.items() if k != "embedded"}, project_dir)
    if resolution.ok and resolution.found is not None:
        return str(resolution.found)
    return None


def _saved_object(project_path: pathlib.Path, name: str, size: int) -> str | None:
    """The address of object *name* in the last save at *project_path*, if it holds *size* bytes.

    A save over the same file (and every autosave) finds embedded data there after its original
    file has gone.
    """
    if not project_path.is_file():
        return None
    from chisurf.core.fio.address import join_address

    from .pto import _tttrlib

    handle = _tttrlib().PtoFile()
    if not handle.open(str(project_path)):
        return None
    try:
        for obj in handle.objects():
            if obj.name == name and int(obj.size) == size:
                return join_address(project_path, name)
    finally:
        handle.close()
    return None


def adopt_saved_links(project: Project, saved: PathLike) -> None:
    """Point this process's live linked datasets at what *saved* now holds.

    Each learns its object name; an embedded one reads from the saved project from now on (so its
    original file may go). Datasets living in another process (server mode) learn it when the
    project is next opened.
    """
    from chisurf.core.fio.address import join_address

    try:
        from chisurf.core.api import dataset_objects

        live = {str(getattr(d, "unique_identifier", "")): d for d in dataset_objects()}
    except Exception:  # noqa: BLE001 - no live session (a script saving a Project)
        return
    for uid, record in project.datasets.items():
        if not isinstance(record, dict) or record.get("kind") != "linked":
            continue
        dataset = live.get(str(record.get("uid", uid)))
        link = record.get("link") or {}
        if dataset is None or not hasattr(dataset, "link") or not link.get("object"):
            continue
        dataset.link = dict(dataset.link, object=link["object"])
        if link.get("embedded"):
            member = f"/{link['member']}" if link.get("member") else ""
            dataset.address = join_address(saved, str(link["object"])) + member
            dataset.link_status, dataset.link_problem = "ok", ""


def _companion_source(primary_source: str, companion_name: str, companion_object: str) -> str:
    """Where a companion's bytes are: beside the primary's file, or in the same project save."""
    from chisurf.core.fio.address import join_address, split_address

    container, member = split_address(primary_source)
    if member and container is not None and str(container).endswith(PROJECT_SUFFIX):
        return join_address(container, companion_object)
    return str(pathlib.Path(primary_source).with_name(companion_name))


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
