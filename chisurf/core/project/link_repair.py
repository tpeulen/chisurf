"""Locate missing data and make a project self-contained: the model behind the *Project data* tool.

A project links its photon streams and other large files (:mod:`chisurf.core.project.links`). This
module is what the user does about those links: see which ones resolve, find a moved original
(search a folder by name, confirm by size and sha256, or point at a file explicitly; a file whose
content differs needs an explicit *Use anyway*, which records its new checksum), and embed every
link so the project no longer needs the files. It is toolkit-free: the *Project data* plugin draws
it, the shell feeds it through a :class:`LinkSource`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from chisurf.core.project import links

__all__ = ["LinkRepairModel", "LinkSource", "ProjectFileSource", "STATE_LABELS"]

#: What each link state reads as in the table.
STATE_LABELS = {
    "ok": "found",
    "embedded": "embedded",
    "missing": "missing",
    "size changed": "size changed",
    "hash changed": "content changed",
}


class LinkSource(Protocol):
    """Where the tool finds the session's linked datasets (the shell implements it)."""

    def linked_datasets(self) -> list[Any]:
        """The live datasets that carry a ``link`` (and ``address``, ``link_status``)."""

    def project_path(self) -> Path | None:
        """The ``.cs.pto`` the session was opened from or saved to, if any."""

    def changed(self) -> None:
        """The datasets' links changed: refresh what shows them."""


class LinkRepairModel:
    """State and actions of the *Project data* tool (drawn from its ``view.json``)."""

    def __init__(self, source: LinkSource | None = None) -> None:
        self.source = source
        self.rows: list[dict] = []
        self.selected: dict = {}
        self.selection: list = []
        self.candidates: list[dict] = []
        self.selected_candidate: dict = {}
        self.candidate_selection: list = []
        self.search_folder = ""
        #: A replacement refused because its content differs, waiting for *Use anyway*.
        self.pending: dict = {}
        self.status_text = ""
        #: ``"open file dialog"`` requests for the app to act on: ``"folder"`` or ``"file"``.
        self.request = ""

    # -- the table ------------------------------------------------------------------- #
    def _datasets(self) -> dict[str, Any]:
        if self.source is None:
            return {}
        return {
            str(getattr(d, "unique_identifier", "")): d
            for d in self.source.linked_datasets()
            if isinstance(getattr(d, "link", None), dict)
        }

    def _project_path(self) -> Path | None:
        return self.source.project_path() if self.source is not None else None

    def refresh(self, *, check_hash: bool = False) -> None:
        """Check every link (size only, unless *check_hash*) and list them."""
        project_path = self._project_path()
        project_dir = project_path.parent if project_path is not None else None
        datasets = self._datasets()
        reports = links.report(
            list(datasets.values()), project_dir, check_hash=check_hash, project_path=project_path
        )
        self.rows = []
        for report in reports:
            state = "embedded" if report.embedded else report.status
            dataset = datasets.get(report.uid)
            if dataset is not None and not report.embedded:
                dataset.link_status, dataset.link_problem = report.status, report.reason
            self.rows.append(
                {
                    "uid": report.uid,
                    "name": report.name,
                    "state": state,
                    "state_label": STATE_LABELS.get(state, state),
                    "location": report.location,
                    "shown": "in the project"
                    if report.embedded
                    else _relative_to(report.location, project_dir),
                    "problem": report.reason or report.location,
                }
            )
        uid = str(self.selected.get("uid", ""))
        self.selected = next((r for r in self.rows if r["uid"] == uid), {})
        refreshed = getattr(self.source, "refreshed", None)
        if callable(refreshed):
            refreshed()  # the link states shown elsewhere (the shell's Source column)

    def _changed(self) -> None:
        """Links were changed: the source is to be saved (and shown) again."""
        if self.source is not None:
            self.source.changed()

    def dataset_rows(self) -> list[dict]:
        """The rows the table shows."""
        return self.rows

    def select_dataset(self, row: Any = None) -> None:
        """A row was chosen: its candidates are searched again for it."""
        self.selected = dict(row) if isinstance(row, dict) else {}
        self.candidates, self.selected_candidate, self.pending = [], {}, {}

    @property
    def unresolved(self) -> list[dict]:
        """The rows whose data is not found (missing, or not the file that was linked)."""
        return [r for r in self.rows if r["state"] in ("missing", "size changed", "hash changed")]

    @property
    def summary_text(self) -> str:
        """One line: how many links, embedded, found and unresolved."""
        if not self.rows:
            return "This project links no data files."
        embedded = sum(r["state"] == "embedded" for r in self.rows)
        found = sum(r["state"] == "ok" for r in self.rows)
        return (
            f"{len(self.rows)} data files: {embedded} embedded, {found} linked and found, "
            f"{len(self.unresolved)} not found or changed."
        )

    @property
    def self_contained(self) -> bool:
        """Whether every linked dataset is embedded (the project needs no other file)."""
        return all(r["state"] == "embedded" for r in self.rows)

    # -- locating --------------------------------------------------------------------- #
    def can_search(self) -> bool:
        """*Search in folder…* needs a selected dataset whose data is not found."""
        return self.selected.get("state") in ("missing", "size changed", "hash changed")

    def can_replace(self) -> bool:
        """*Replace with…* needs a selected linked (not embedded) dataset."""
        return bool(self.selected) and self.selected.get("state") != "embedded"

    def can_use_anyway(self) -> bool:
        """*Use anyway* waits for a replacement that was refused as a different file."""
        return bool(self.pending)

    def request_search(self) -> None:
        """Ask the app for a folder to search."""
        if self.can_search():
            self.request = "folder"

    def request_replace(self) -> None:
        """Ask the app for the file to use instead."""
        if self.can_replace():
            self.request = "file"

    def search(self, folder: str | Path) -> list[dict]:
        """Files under *folder* named like the selected dataset's file, recorded size first."""
        dataset = self._datasets().get(str(self.selected.get("uid", "")))
        self.search_folder = str(folder)
        self.candidates, self.selected_candidate = [], {}
        if dataset is None:
            return []
        found = links.find_candidates(dataset.link, folder, project_path=self._project_path())
        self.candidates = [
            {
                "path": str(c.path),
                "shown": _relative_to(c.path, folder),
                "size": c.size,
                "match": "same size" if c.size_matches else "other size",
            }
            for c in found
        ]
        if self.candidates:
            self.selected_candidate = self.candidates[0]
            self.status_text = (
                f"{len(self.candidates)} file(s) named {Path(self.candidates[0]['path']).name} "
                f"under {folder}; Use candidate checks the best one by its checksum."
            )
        else:
            self.status_text = f"No file of that name under {folder}."
        return self.candidates

    def search_mmfdb(self, *, transport: Any = None) -> list[dict]:
        """MMFDB objects with the selected dataset's checksum: copies it can be read from.

        The store is content-addressed, so a match by sha256 is the same file wherever it lives.
        """
        from chisurf.core.project import remote_links

        dataset = self._datasets().get(str(self.selected.get("uid", "")))
        self.candidates, self.selected_candidate = [], {}
        if dataset is None:
            return []
        copies = remote_links.find_copies(str(dataset.link.get("sha256", "")), transport=transport)
        self.candidates = [
            {
                "path": c["uri"],
                "shown": f"MMFDB: {c['name']}" + (f" ({c['server']})" if c["server"] else ""),
                "size": int(dataset.link.get("size", 0)),
                "match": "same checksum",
                "mmfdb": True,
            }
            for c in copies
        ]
        if self.candidates:
            self.selected_candidate = self.candidates[0]
            self.status_text = (
                f"{len(self.candidates)} MMFDB object(s) with this file's checksum; "
                "Use candidate reads the dataset from MMFDB."
            )
        else:
            self.status_text = "No MMFDB object with this file's checksum (or no MMFDB session)."
        return self.candidates

    def use_mmfdb_copy(self, uri: str) -> bool:
        """Read the selected dataset from the MMFDB object *uri* (same checksum), fetched first."""
        from chisurf.core.project import remote_links

        uid = str(self.selected.get("uid", ""))
        dataset = self._datasets().get(uid)
        if dataset is None:
            self.status_text = "Select a dataset first."
            return False
        dataset.link = links.use_remote_copy(dataset.link, uri)
        fetch = getattr(self.source, "prefetch_links", None)
        if callable(fetch):
            fetch([dataset])
        else:
            remote_links.prefetch([dataset.link])
        resolution = links.resolve(dataset.link)
        dataset.link_status, dataset.link_problem = resolution.status, resolution.reason
        self._changed()
        self.status_text = (
            f"{dataset.name} is read from MMFDB ({uri}). Save the project to keep it."
        )
        self.refresh()
        return True

    def candidate_rows(self) -> list[dict]:
        """The candidates the search found."""
        return self.candidates

    def select_candidate(self, row: Any = None) -> None:
        """A candidate was chosen."""
        self.selected_candidate = dict(row) if isinstance(row, dict) else {}

    def can_use_candidate(self) -> bool:
        """*Use candidate* needs a chosen candidate for a dataset that is still not found."""
        return bool(self.selected_candidate) and self.can_search()

    def use_candidate(self) -> bool:
        """Relink the selected dataset to the chosen candidate (size and sha256 checked)."""
        if not self.selected_candidate:
            return False
        if self.selected_candidate.get("mmfdb"):
            done = self.use_mmfdb_copy(self.selected_candidate["path"])
            if done:
                self.candidates, self.selected_candidate = [], {}
            return done
        done = self.replace(self.selected_candidate["path"])
        if done:
            self.candidates, self.selected_candidate = [], {}
        return done

    def replace(self, path: str | Path, *, force: bool = False) -> bool:
        """Point the selected dataset at *path*; a different file waits for *Use anyway*."""
        uid = str(self.selected.get("uid", ""))
        dataset = self._datasets().get(uid)
        if dataset is None:
            self.status_text = "Select a dataset first."
            return False
        try:
            link = links.relink(dataset.link, path, force=force)
        except links.LinkError as exc:
            self.pending = {"uid": uid, "path": str(path)}
            self.status_text = f"{exc}. Use anyway records it as the dataset's file."
            return False
        project_path = self._project_path()
        if project_path is not None:
            link = links.relativize(link, project_path.parent)
        dataset.link = link
        member = link.get("member")
        dataset.address = f"{link['container']}/{member}" if member else link["container"]
        dataset.link_status, dataset.link_problem = "ok", ""
        self.pending = {}
        self._changed()
        self.status_text = (
            f"{dataset.name} now reads {Path(str(path)).name}"
            + (" (a different file: its new checksum is recorded)." if force else ".")
            + " Save the project to keep it."
        )
        self.refresh()
        return True

    def use_anyway(self) -> bool:
        """Accept the refused replacement: it becomes the dataset's file, with its own checksum."""
        if not self.pending:
            return False
        self.selected = next(
            (r for r in self.rows if r["uid"] == self.pending["uid"]), self.selected
        )
        return self.replace(self.pending["path"], force=True)

    # -- self-contained ----------------------------------------------------------------- #
    def can_make_self_contained(self) -> bool:
        """*Make self-contained* needs linked datasets that are not embedded yet."""
        return any(r["state"] != "embedded" for r in self.rows)

    def make_self_contained(self) -> list[str]:
        """Embed every linked dataset (each checked by its sha256); unresolved ones are listed.

        Returns the names that could not be embedded; with any, nothing is embedded and the
        status says to locate them first. The bytes go into the project at its next save.
        """
        self.refresh()
        if self.unresolved:
            names = ", ".join(r["name"] for r in self.unresolved)
            self.status_text = f"Locate these first, then make the project self-contained: {names}."
            return [r["name"] for r in self.unresolved]
        project_path = self._project_path()
        project_dir = project_path.parent if project_path is not None else None
        failed: list[str] = []
        datasets = self._datasets()
        for row in self.rows:
            dataset = datasets.get(row["uid"])
            if dataset is None or links.is_embedded(dataset.link):
                continue
            try:
                dataset.link = links.embed(dataset.link, project_dir)
            except links.LinkError as exc:
                failed.append(f"{row['name']} ({exc})")
        self._changed()
        self.refresh()
        if failed:
            self.status_text = "Not embedded: " + "; ".join(failed)
        else:
            self.status_text = (
                "Every data file will be stored in the project at the next save; "
                "the project then needs no other file."
            )
        return failed


def _relative_to(path: Any, base: Any) -> str:
    """*path* relative to *base* when it lies below it (``data/a.tif``), else as it is."""
    import os

    if not path:
        return ""
    if base is None:
        return str(path)
    try:
        relative = os.path.relpath(Path(path).resolve(), Path(base).resolve())
    except ValueError:
        return str(path)
    return relative if not relative.startswith(".." + os.sep + ".." + os.sep) else str(path)


class _RecordDataset:
    """A linked dataset record of a project file, shaped like a live linked dataset."""

    def __init__(self, record: dict) -> None:
        self._record = record
        self.unique_identifier = str(record.get("uid", ""))
        self.name = str(record.get("name", ""))
        self.link_status = "ok"
        self.link_problem = ""

    @property
    def link(self) -> dict:
        return self._record["link"]

    @link.setter
    def link(self, value: dict) -> None:
        self._record["link"] = dict(value)

    @property
    def address(self) -> str:
        return str(self._record.get("address", ""))

    @address.setter
    def address(self, value: str) -> None:
        self._record["address"] = str(value)


class ProjectFileSource:
    """A saved ``.cs.pto`` as the tool's source: repair its links without opening it in ChiSurf.

    The datasets are the project's linked records; :meth:`save` writes the project back (the
    embedded bytes go in then).
    """

    def __init__(self, path: str | Path) -> None:
        from chisurf.core.project.project import Project

        self.path = Path(path)
        self.project = Project.load(self.path)
        self.records = [
            _RecordDataset(record)
            for record in self.project.datasets.values()
            if isinstance(record, dict) and record.get("kind") == "linked"
        ]
        self.dirty = False

    def linked_datasets(self) -> list[Any]:
        return self.records

    def project_path(self) -> Path | None:
        return self.path

    def changed(self) -> None:
        self.dirty = True

    def save(self) -> Path:
        """Write the project back to its file (embedding what is marked embedded).

        Its own graph session goes back with it -- never the running session's, which a
        storage save would capture into this unrelated file.
        """
        import json

        from chisurf.core.project.archive import ProjectArchive
        from chisurf.core.project.pto import SESSION_FILENAME

        project = self.project
        project.relativize_links(self.path.parent)
        files = project.data_files(self.path)
        archive = ProjectArchive()
        archive.write_text("project.json", json.dumps(project.to_dict(), indent=2, sort_keys=True))
        project.resources.write_to_archive(archive)
        session = getattr(project, "graph_session_bytes", None)
        if session is not None:
            archive.write_bytes(SESSION_FILENAME, session)
        saved = archive.save(self.path, files=files)
        project.source_path, project.source_dir = saved, saved.parent
        self.dirty = False
        return saved
