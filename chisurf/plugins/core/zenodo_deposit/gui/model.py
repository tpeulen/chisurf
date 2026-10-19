"""Qt-free model of the Zenodo deposit tool: review a record, then upload it.

Every record that goes to Zenodo is checked here first. A record is a folder
with its review state beside it (``<record>.deposit.json``, see
:mod:`mmfdb.deposit`): one item per measurement folder, calibration folder and
metadata file, each with where it came from, what it holds and the flags that
say why it needs a closer look. The reviewer approves or rejects item by
item; an approval is bound to the item's content, so anything that changes
afterwards is pending again. Upload and publish stay grey until
:func:`mmfdb.deposit.blockers` is empty -- the same gate the CLI uses.

Package builds, uploads and remote checks run on a worker so the window stays
live while a gigabyte moves.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from mmfdb.deposit import (
    DepositRecord,
    GateError,
    ZenodoClient,
    blockers,
    build_package,
    compare,
    credentials,
    publish,
    refresh_metadata_item,
    refresh_remote,
    scan,
    upload,
)
from mmfdb.deposit.compose import (
    ACCESS_RIGHTS,
    LICENSES,
    UPLOAD_TYPES,
    add_data,
    new_record,
    template,
    valid_name,
    zenodo_problems,
)
from mmfdb.deposit.record import METADATA_ITEM

from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

#: Where records live unless the user points elsewhere (an external disk:
#: the data passes through this machine for review).
DEFAULT_ROOT = "/Volumes/SD1TB/T4L_Unfolded/records"
#: Record build configs and the commands that build and scan one (T4L defaults).
DEFAULT_CONFIGS = "/Users/tpeulen/projects/T4L_Unfolded/scripts/records"
DEFAULT_BUILD = ("{python} /Users/tpeulen/projects/T4L_Unfolded/scripts/build_record.py {config}")
DEFAULT_SCAN = ("{python} /Users/tpeulen/projects/T4L_Unfolded/scripts/review_record.py {record}")
#: Where packages are written: beside the records folder.
ZIPS = "zips"

STATUS_LABELS = {"pending": "Pending", "approved": "Approved", "rejected": "Rejected"}
SANDBOX = "https://sandbox.zenodo.org/api"
PRODUCTION = "https://zenodo.org/api"


def _md(text: str) -> str:
    """Text shown verbatim inside markdown.

    File globs carry ``*``, which markdown would read as emphasis, and emtk's
    renderer has no backslash escapes -- so a word holding one is shown as
    code instead. (Underscores inside words are kept as they are.)
    """
    return " ".join(f"`{w}`" if "*" in w and "`" not in w else w for w in str(text).split(" "))


def _size(n: int) -> str:
    for unit, scale in (("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if n >= scale:
            return f"{n / scale:,.1f} {unit}"
    return f"{n} B"


class ZenodoDepositModel:
    """The records under a folder, the selected record's items and its gate."""

    def __init__(self, client_factory=None, ndx_opener=None, runner=None) -> None:
        self.data_root = os.environ.get("MMFDB_DEPOSIT_ROOT", DEFAULT_ROOT)
        #: Where record build configs live (one JSON per record) and the commands
        #: that turn one into a record and then scan it. ``{config}`` and
        #: ``{record}`` are filled in; a project sets its own in the settings.
        self.configs_dir = os.environ.get("MMFDB_DEPOSIT_CONFIGS", DEFAULT_CONFIGS)
        self.build_command = DEFAULT_BUILD
        self.scan_command = DEFAULT_SCAN
        self.config_name = ""
        self.build_log = ""
        #: Step 1 -- a new record by hand.
        self.new_name = ""
        self.new_title = ""
        #: Step 2 -- what the next files are added as.
        self.add_role = "measurement"
        self.add_name = ""
        self.add_group = ""
        #: How a selected Markdown file is shown: ``Preview`` (rendered) or ``Source``.
        self.md_mode = "Preview"
        #: ``"files"`` or ``"folder"`` while the host should show its file dialog.
        self.pick = ""
        #: Where the file dialog opens: the last folder something was added from.
        self.pick_directory = os.path.expanduser("~")
        self._runner = runner
        self.note = ""
        self.sandbox = False
        #: What is typed in the token field; cleared once it is stored.
        self.token_entry = ""
        self.token_check = ""
        self.record: DepositRecord | None = None
        self.item_id = ""
        self.message = ""
        self.job = BackgroundJob()
        self.busy_what = ""
        self._client_factory = client_factory or (lambda base: ZenodoClient(base=base))
        #: ``opener(path)`` -- ndX's ``open_in_ndx`` unless a test supplies one.
        self._ndx_opener = ndx_opener
        self.refresh_records()

    # ── records under the root ───────────────────────────────────────────
    def refresh_records(self) -> None:
        """Re-list the records under the data root (the action and Enter in the field)."""
        root = Path(self.data_root)
        self._records = []
        for p in sorted(root.glob("*.deposit.json")) if root.is_dir() else []:
            try:
                rec = DepositRecord.load(p)
            except (ValueError, OSError) as exc:
                self._records.append({"name": p.name, "state": f"unreadable: {exc}",
                                      "review": "", "remote": ""})
                continue
            self._records.append(self._record_row(rec))
        unscanned = [d for d in sorted(root.iterdir()) if d.is_dir()
                     and not (root / f"{d.name}.deposit.json").exists()] if root.is_dir() else []
        for d in unscanned:
            self._records.append({"name": d.name, "state": "not scanned", "review": "",
                                  "remote": ""})

    @staticmethod
    def _record_row(rec: DepositRecord) -> dict:
        c = rec.counts()
        b = blockers(rec)
        return {"name": rec.name,
                "state": "cleared for upload" if not b else f"{len(b)} blocking",
                "review": f"{c['approved']}/{len(rec.items)} approved"
                          + (f", {c['rejected']} rejected" if c["rejected"] else ""),
                "remote": (f"draft {rec.remote['deposition_id']}"
                           if rec.remote.get("deposition_id") else "not uploaded")
                          + (" (published)" if rec.remote.get("doi") else "")}

    @property
    def records(self) -> list[dict]:
        return self._records

    def select_record(self, row: dict | None) -> None:
        """Open the record a row names (scanning it first when it has no review yet)."""
        if not row:
            return
        folder = Path(self.data_root) / row["name"]
        try:
            self.record = (DepositRecord.load(folder) if row["state"] != "not scanned"
                           else scan(folder))
            if not self.record.metadata:
                # The form shows what is stored: an empty record gets the template
                # (dataset, open, cc-by-4.0, today), not choices that only look set.
                self.record.metadata = template(self.record.title)
                refresh_metadata_item(self.record)
                row = {**row, "state": "not scanned"}
            if row["state"] == "not scanned":
                self.record.save()
                self.refresh_records()
        except Exception as exc:  # noqa: BLE001 - shown to the reviewer
            self.record, self.message = None, f"could not open {row['name']}: {exc}"
            return
        self.item_id = ""
        self.message = f"opened {self.record.name}"

    # ── step 1: a new record by hand ─────────────────────────────────────
    @property
    def has_record(self) -> str:
        """``"yes"`` while a record is open: steps 2-4 are shown only then."""
        return "yes" if self.record is not None else "no"

    no_record_hint = ("**Steps 2-4** (add data, Zenodo metadata, scan) appear once a record is "
                      "open: create one above, or click one in the list at the top.")

    @property
    def new_name_problem(self) -> str:
        name = self.new_name.strip()
        if not name:
            return ("Type a name: lower case, no spaces, e.g. `t4l-unfolding-smfret-k60-n132c`. "
                    "It becomes the folder and the archive name.")
        if (Path(self.data_root) / name).exists():
            return f"**{name}** exists already -- pick it in the list above instead."
        problem = valid_name(name)
        return f"**Not a valid name:** {problem}." if problem else (
            f"Creates `{Path(self.data_root) / name}` with empty measurements/ and calibrations/.")

    def create_record(self) -> None:
        """Make the empty record, open it, and fill the metadata template with the title."""
        try:
            rec = new_record(self.data_root, self.new_name.strip(), self.new_title.strip())
        except (ValueError, FileExistsError, OSError) as exc:
            self.message = f"could not create the record: {exc}"
            return
        self.record = scan(rec.folder)
        self.record.save()
        self.item_id = ""
        self.new_name = self.new_title = ""
        self.refresh_records()
        self.message = (f"created {rec.name} -- now add its data (step 2) and fill in the "
                        "Zenodo metadata (step 3)")

    # ── step 2: data into the record ─────────────────────────────────────
    ADD_ROLES = ("measurement", "calibration")

    @property
    def add_target(self) -> str:
        """Where the next files land, in words, or why they cannot be added yet."""
        if self.record is None:
            return "Create or pick a record first."
        name = self.add_name.strip()
        if not name:
            return ("Name the item first: one folder, e.g. `2014-08-12_0M-urea` for a "
                    "measurement or `h2o-scatter` for a calibration.")
        if self.add_role == "calibration":
            if not self.add_group.strip():
                return ("A calibration belongs to a group: the setup and day it calibrates, "
                        "e.g. `2014-08-12_pq-hydraharp`.")
            rel = f"calibrations/{self.add_group.strip()}/{name}"
        else:
            rel = f"measurements/{name}"
        return (f"Files and folders you choose go to `{rel}/` -- hard-linked when on the same "
                "disk, copied otherwise. Nothing is overwritten.")

    def _can_add(self) -> bool:
        return (self.record is not None and bool(self.add_name.strip())
                and (self.add_role != "calibration" or bool(self.add_group.strip())))

    def add_files(self) -> None:
        self.pick = "files"

    def add_folder(self) -> None:
        self.pick = "folder"

    def add_paths(self, paths) -> None:
        """The file dialog's answer: put *paths* into the record as the named item."""
        self.pick = ""
        if not paths or self.record is None:
            return
        try:
            r = add_data(self.record, paths, self.add_role, self.add_name.strip(),
                         self.add_group.strip())
        except (ValueError, FileExistsError, FileNotFoundError, OSError) as exc:
            self.message = f"nothing added: {exc}"
            return
        self.record = scan(self.record.folder)
        self.record.save()
        self.refresh_records()
        self.message = (f"{r['item']}: {r['linked']} linked, {r['copied']} copied"
                        + (f", {r['present']} already there" if r["present"] else ""))

    def show_folder(self) -> None:
        """Open the record folder in the file manager (files dropped there count on Rescan)."""
        if self.record is None:
            return
        import subprocess
        import sys

        opener = {"darwin": "open", "win32": "explorer"}.get(sys.platform, "xdg-open")
        subprocess.Popen([opener, str(self.record.folder)])

    @property
    def record_tree(self) -> str:
        """The record's layout: every item folder with its file count and size."""
        if self.record is None:
            return ""
        lines = []
        for i in self.record.items:
            if i.id == METADATA_ITEM:
                continue
            lines.append(f"{i.id:<60} {i.files:>5} files {_size(i.bytes):>10}")
        return "\n".join(lines) or "(empty -- add a measurement and its calibrations)"

    # ── step 3: the Zenodo metadata ──────────────────────────────────────
    UPLOAD_TYPES = UPLOAD_TYPES
    LICENSES = LICENSES
    ACCESS_RIGHTS = ACCESS_RIGHTS

    def _meta(self) -> dict:
        return self.record.metadata if self.record is not None else {}

    def _set_meta(self, key: str, value) -> None:
        """Write one field, re-check it, and void its approval if it changed -- no rescan."""
        if self.record is None:
            return
        m = self.record.metadata
        empty = value in ("", [], None)
        if (m.get(key) == value) or (empty and key not in m):
            return
        if empty:
            m.pop(key, None)
        else:
            m[key] = value
        refresh_metadata_item(self.record)
        self.record.save()
        self.refresh_records()

    def _text_field(key):  # noqa: N805 - a property factory used in the class body
        return property(lambda self: str(self._meta().get(key, "")),
                        lambda self, v: self._set_meta(key, str(v).strip()))

    meta_title = _text_field("title")
    meta_upload_type = _text_field("upload_type")
    meta_publication_date = _text_field("publication_date")
    meta_license = _text_field("license")
    meta_access_right = _text_field("access_right")
    meta_version = _text_field("version")
    meta_embargo_date = _text_field("embargo_date")
    del _text_field

    @property
    def meta_description(self) -> str:
        return str(self._meta().get("description", ""))

    @meta_description.setter
    def meta_description(self, v: str) -> None:
        self._set_meta("description", str(v).strip())

    @property
    def meta_creators(self) -> str:
        """One creator per line: ``Family, Given; Affiliation; ORCID``."""
        lines = []
        for c in self._meta().get("creators", []):
            parts = [c.get("name", ""), c.get("affiliation", ""), c.get("orcid", "")]
            while parts and not parts[-1]:
                parts.pop()
            lines.append("; ".join(parts))
        return "\n".join(lines)

    @meta_creators.setter
    def meta_creators(self, text: str) -> None:
        creators = []
        for line in str(text).splitlines():
            parts = [p.strip() for p in line.split(";")]
            if not parts or not parts[0]:
                continue
            c = {"name": parts[0]}
            if len(parts) > 1 and parts[1]:
                c["affiliation"] = parts[1]
            if len(parts) > 2 and parts[2]:
                c["orcid"] = parts[2]
            creators.append(c)
        self._set_meta("creators", creators)

    @property
    def meta_keywords(self) -> str:
        return ", ".join(self._meta().get("keywords", []))

    @meta_keywords.setter
    def meta_keywords(self, text: str) -> None:
        self._set_meta("keywords", [k.strip() for k in str(text).split(",") if k.strip()])

    @property
    def meta_related(self) -> str:
        """One related identifier per line: ``relation identifier`` (e.g. a paper DOI)."""
        return "\n".join(f"{r.get('relation', '')} {r.get('identifier', '')}"
                         for r in self._meta().get("related_identifiers", []))

    @meta_related.setter
    def meta_related(self, text: str) -> None:
        rel = []
        for line in str(text).splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                rel.append({"relation": parts[0], "identifier": parts[1].strip()})
            elif parts:
                rel.append({"relation": "", "identifier": parts[0]})
        self._set_meta("related_identifiers", rel)

    @property
    def meta_access_is_embargoed(self) -> str:
        return "yes" if self._meta().get("access_right") == "embargoed" else "no"

    @property
    def metadata_status(self) -> str:
        """Whether the metadata is a complete deposition, and where it comes from."""
        if self.record is None:
            return "Create or pick a record first."
        problems = zenodo_problems(self.record.metadata)
        built = (Path(self.configs_dir) / f"{self.record.name}.json").is_file()
        head = ("**This record is built from a config:** edits here are replaced the next time "
                "it is built -- change the config's \"zenodo\" block instead.\n\n" if built else "")
        if problems:
            return head + f"**{len(problems)} to fix before upload:**\n" + "\n".join(
                f"- {_md(p)}" for p in problems)
        return head + ("**Complete.** It is reviewed like any item: approve *Zenodo metadata* in "
                       "*1 · Review*. Any later edit voids that approval.")

    @property
    def metadata_json(self) -> str:
        """Exactly what is sent to Zenodo as the deposition metadata."""
        import json

        return json.dumps(self._meta(), indent=2, ensure_ascii=False) if self.record else ""

    # ── step 4 ───────────────────────────────────────────────────────────
    def scan_for_review(self) -> None:
        """Re-read the record after adding data: the items a reviewer then judges."""
        self.rescan()
        if self.record is not None:
            self.message = (f"{len(self.record.items)} items to review -- open *1 · Review*")

    # ── creating a record from its build config ──────────────────────────
    @property
    def configs(self) -> list[dict]:
        """One row per build config: has its record been built, scanned, uploaded?"""
        d = Path(self.configs_dir)
        rows = []
        for p in sorted(d.glob("*.json")) if d.is_dir() else []:
            name = p.stem
            folder = Path(self.data_root) / name
            review = Path(self.data_root) / f"{name}.deposit.json"
            state = ("not built" if not folder.is_dir() else
                     "built, not scanned" if not review.is_file() else "built and scanned")
            built = (time.strftime("%Y-%m-%d %H:%M", time.localtime(folder.stat().st_mtime))
                     if folder.is_dir() else "")
            rows.append({"name": name, "state": state, "built": built, "config": str(p)})
        return rows

    def select_config(self, row: dict | None) -> None:
        self.config_name = row["name"] if row else ""

    @property
    def config_text(self) -> str:
        p = Path(self.configs_dir) / f"{self.config_name}.json"
        return p.read_text(encoding="utf-8") if self.config_name and p.is_file() else ""

    def build_record(self) -> None:
        """Build the selected config into a record, then scan it -- on the worker.

        Rebuilding replaces the record folder: approvals of items whose content
        changed are void (they are bound to the content), the others stand.
        """
        if not self.config_name:
            return
        import shlex
        import subprocess
        import sys

        cfg = str(Path(self.configs_dir) / f"{self.config_name}.json")
        rec = str(Path(self.data_root) / self.config_name)
        cmds = [c.format(python=shlex.quote(sys.executable), config=shlex.quote(cfg),
                         record=shlex.quote(rec)) for c in (self.build_command, self.scan_command)]
        run = self._runner or (lambda cmd: subprocess.run(
            cmd, shell=True, capture_output=True, text=True, env={
                k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}))
        self.busy_what = f"building {self.config_name}"
        self.build_log = ""

        def work():
            log = []
            for cmd in cmds:
                r = run(cmd)
                out = (r.stdout or "") + (r.stderr or "")
                log.append(f"$ {cmd}\n" + "\n".join(
                    ln for ln in out.splitlines() if "Removed 1 path" not in ln)[-6000:])
                if r.returncode != 0:
                    raise RuntimeError("\n\n".join(log))
            return "\n\n".join(log)

        def done(log):
            self.build_log = log
            self.message = f"built {self.config_name}" + (
                " -- VERIFY_OK" if "VERIFY_OK" in log else " -- check the log")
            self.refresh_records()

        def fail(exc):
            self.build_log = str(exc)
            self.message = f"building {self.config_name} failed (see the log)"

        self.job.start(work, done, fail)

    # ── what is submitted to Zenodo ───────────────────────────────────────
    @property
    def zenodo_text(self) -> str:
        """The deposition metadata of the selected record, for review before upload."""
        if self.record is None:
            return ""
        m = self.record.metadata or {}
        if not m:
            return "**No Zenodo metadata** -- fill it in *0 · Create*, step 3."
        lines = [f"**Title:** {_md(m.get('title', ''))}", "", "**Creators:**", ""] + [
            f"- {c.get('name')} -- {c.get('affiliation', '')}" for c in m.get("creators", [])
        ] + ["", f"**License:** {m.get('license', '')} · **Type:** {m.get('upload_type', '')} · "
                 f"**Access:** {m.get('access_right', '')}", "",
                 "**Keywords:** " + ", ".join(m.get("keywords", []))]
        if m.get("notes"):
            lines += ["", f"**Notes:** {_md(m['notes'])}"]
        return "\n".join(lines)

    @property
    def zenodo_description(self) -> str:
        """The description, one sentence per line (it is a single HTML paragraph)."""
        text = (self.record.metadata or {}).get("description", "") if self.record else ""
        return re.sub(r"(?<=[.;]) (?=[A-Z<])", "\n", text)

    # ── items of the selected record ─────────────────────────────────────
    @property
    def items(self) -> list[dict]:
        if self.record is None:
            return []
        return [{"id": i.id, "status": STATUS_LABELS.get(i.status, i.status)
                 + (" (changed)" if i.review.status == "approved" and i.status != "approved"
                    else ""),
                 "role": i.role, "group": i.group, "files": i.files,
                 "size": _size(i.bytes),
                 "holds": (f"{i.files} file{'s' if i.files != 1 else ''} · " if i.files
                           else "JSON · ") + _size(i.bytes),
                 "flags": ("✖ " if i.errors else "") + (f"⚠ {len(i.flags)}" if i.flags else ""),
                 "act": "" if i.status == "approved" or self.job.running else "Approve",
                 "detail": self._item_tooltip(i)}
                for i in self.record.items]

    @staticmethod
    def _item_tooltip(it) -> str:
        """The row's tooltip: what the item is and where it came from, its flags first."""
        lines = [f"✖ {e}" for e in it.errors[:6]] + [f"⚠ {f}" for f in it.flags]
        if it.description:
            lines.append(it.description)
        if it.origin:
            lines.append(f"from {it.origin}")
        r = it.review
        if r.status != "pending" or r.by:
            lines.append(f"{r.status} by {r.by} at {r.at}" + (f": {r.note}" if r.note else ""))
        return "\n".join(lines)

    def select_item(self, row: dict | None) -> None:
        self.item_id = row["id"] if row else ""
        self.note = ""

    @property
    def item(self):
        if self.record is None or not self.item_id:
            return None
        try:
            return self.record.item(self.item_id)
        except KeyError:
            return None

    @property
    def item_text(self) -> str:
        """The selected item in a few lines: what to check first, then what it is.

        Where it came from and the review so far are in the row's tooltip.
        """
        it = self.item
        if it is None:
            return "Select a row; approve it with its button or right-click it for more."
        lines = [f"✖ blocks the upload: {_md(e)}" for e in it.errors[:12]] \
            + [f"⚠ {_md(f)}" for f in it.flags]
        about = [_md(it.id), f"{it.files} file{'s' if it.files != 1 else ''}, {_size(it.bytes)}"]
        if it.description:
            about.append(_md(it.description))
        r = it.review
        if r.status != "pending":
            about.append(r.status + (" (content changed since)" if it.status != r.status else ""))
        lines.append(" · ".join(about))
        return "\n\n".join(lines)

    @property
    def open_record(self) -> DepositRecord:
        """The record being reviewed; raises when none is open (callers gate on ``has_rec``)."""
        if self.record is None:
            raise RuntimeError("no deposit record is open")
        return self.record

    # ── the selected metadata file, for the code editor ──────────────────
    @property
    def preview_kind(self) -> str:
        """``json``, ``mmcif``, ``markdown``, ``text``, ``listing`` (a folder) or ``none``."""
        it = self.item
        if it is None:
            return "none"
        if it.id == METADATA_ITEM:
            return "json"
        p = self.open_record.folder / it.id
        if p.is_dir():
            return "listing"
        if not p.is_file():
            return "none"
        return {".json": "json", ".cif": "mmcif", ".md": "markdown"}.get(p.suffix.lower(), "text")

    @property
    def editor_kind(self) -> str:
        """Which code editor shows the selection: a folder listing is plain text."""
        kind = self.preview_kind
        return "text" if kind == "listing" else kind

    @property
    def preview_text(self) -> str:
        kind = self.preview_kind
        if kind == "none":
            return ""
        if self.item.id == METADATA_ITEM:
            return self.metadata_json
        p = self.open_record.folder / self.item.id
        if kind == "listing":
            from mmfdb.deposit.record import content_files

            files = content_files(p)
            width = max((len(f.relative_to(p).as_posix()) for f in files), default=0)
            return "\n".join(f"{f.relative_to(p).as_posix():<{width}}  {_size(f.stat().st_size):>10}"
                             for f in files)
        text = p.read_text(errors="replace")
        return text if len(text) < 2_000_000 else text[:2_000_000] + "\n… (truncated)"

    # ── ndX ──────────────────────────────────────────────────────────────
    @property
    def ndx_container(self) -> Path | None:
        """The burst-analysis container of the selected item, if it has one."""
        it = self.item
        return None if it is None else self._container_of(it.id)

    def _container_of(self, item_id: str) -> Path | None:
        if self.record is None or not item_id or item_id == METADATA_ITEM:
            return None
        p = self.record.folder / item_id
        if p.is_file():
            return p if p.name.endswith(".pto") else None
        return next(iter(sorted(p.glob("*.mmfdb.pto"))), None) if p.is_dir() else None

    def open_in_ndx(self, row: dict | None = None) -> None:
        """Open the item's container in ndX, to look at the bursts before approving."""
        self._pick_row(row)
        path = self.ndx_container
        if path is None:
            return
        try:
            if self._ndx_opener is not None:
                self._ndx_opener(path)
            else:
                from chisurf.plugins.ndxplorer.gui.app import open_in_ndx

                open_in_ndx(path)
            self.message = f"opened {path.name} in ndX"
        except Exception as exc:  # noqa: BLE001 - shown to the reviewer
            self.message = f"could not open {path.name} in ndX: {exc}"

    # One attribute per editor: an emtk code editor is keyed by its target and
    # keeps the language it was created with.
    @property
    def preview_json(self) -> str:
        return self.preview_text if self.preview_kind == "json" else ""

    @property
    def preview_cif(self) -> str:
        return self.preview_text if self.preview_kind == "mmcif" else ""

    @property
    def md_view(self) -> str:
        """``preview`` or ``source`` for a selected Markdown file, else ``""``."""
        if self.preview_kind != "markdown":
            return ""
        return "source" if self.md_mode == "Source" else "preview"

    @property
    def preview_md_rendered(self) -> str:
        return self.preview_md if self.md_view == "preview" else ""

    @property
    def preview_md(self) -> str:
        return self.preview_text if self.preview_kind == "markdown" else ""

    @property
    def preview_txt(self) -> str:
        return self.preview_text if self.preview_kind in ("text", "listing") else ""

    # ── review ───────────────────────────────────────────────────────────
    def _pick_row(self, row: dict | None) -> None:
        """Act on *row* (a table button or menu); the note typed stays with its own item."""
        if row and row.get("id") != self.item_id:
            self.select_item(row)

    def can_approve(self, row: dict | None = None) -> bool:
        return bool(row and row.get("act")) if row is not None else self.enabled("approve_item")

    def can_approve_all(self, row: dict | None = None) -> bool:
        return self.enabled("approve_all")

    def can_decide(self, row: dict | None = None) -> bool:
        return not self.job.running and self.record is not None

    def has_ndx(self, row: dict | None = None) -> bool:
        if row is None:
            return self.ndx_container is not None
        return self._container_of(row.get("id", "")) is not None

    def _review(self, status: str, row: dict | None = None) -> None:
        self._pick_row(row)
        if self.record is None or self.item is None:
            return
        self.record.set_review(self.item_id, status, self.note.strip())
        self.record.save()
        self.message = f"{status}: {self.item_id}"
        self.note = ""
        self.refresh_records()

    def approve_item(self, row: dict | None = None) -> None:
        self._review("approved", row)

    def _approvable(self) -> list:
        """What *Approve all* approves: every item not decided yet that passes the machine check.

        A rejection stands (it was a decision); an item failing the check is left
        to be fixed -- approving it would not clear the gate.
        """
        if self.record is None:
            return []
        return [i for i in self.record.items
                if i.status != "approved" and i.review.status != "rejected" and not i.errors]

    def approve_all_label(self) -> str:
        n = len(self._approvable())
        return f"Approve all ({n})" if n else "Approve all"

    def approve_all(self, row: dict | None = None) -> None:
        """Approve every open item at its current content, each with the note "approve all"."""
        todo = self._approvable()
        if not todo or self.job.running:
            return
        note = self.note.strip()
        for it in todo:
            self.record.set_review(it.id, "approved", "approve all" + (f": {note}" if note else ""))
        self.record.save()
        flagged = sum(1 for it in todo if it.flags)
        self.message = (f"approved {len(todo)} item(s)"
                        + (f", {flagged} of them flagged" if flagged else ""))
        self.note = ""
        self.refresh_records()

    def reject_item(self, row: dict | None = None) -> None:
        self._review("rejected", row)

    def reset_item(self, row: dict | None = None) -> None:
        self._review("pending", row)

    def rescan(self) -> None:
        """Re-read the record folder: new digests, kept reviews, changed items pending."""
        if self.record is None:
            return
        self.record = scan(self.record.folder)
        self.record.save()
        self.refresh_records()
        self.message = "rescanned: approvals of changed items are void"

    # ── the gate ─────────────────────────────────────────────────────────
    @property
    def gate_text(self) -> str:
        if self.record is None:
            return "Open a record."
        b = blockers(self.record)
        pkg = self.record.package
        head = (f"Package: `{Path(pkg['path']).name}`, {pkg['bytes']:,} B, md5 `{pkg['md5']}`"
                if pkg.get("path") else "Package: not built")
        if not b:
            return f"{head}\n\n**Cleared for upload.**"
        shown = "\n".join(f"- {_md(x)}" for x in b[:8]) + (f"\n- … {len(b) - 8} more" if len(b) > 8
                                                      else "")
        return f"{head}\n\n**{len(b)} blocking:**\n{shown}"

    @property
    def remote_text(self) -> str:
        if self.record is None:
            return ""
        r = self.record.remote
        if not r.get("deposition_id"):
            return "Zenodo: not uploaded."
        diff = compare(self.record)
        return (f"Zenodo draft {r['deposition_id']} ({r.get('state', '?')}), checked "
                f"{r.get('checked_at', 'never')}: "
                + ("matches the package." if not diff else "; ".join(diff))
                + (f" DOI {r['doi']}" if r.get("doi") else ""))

    @property
    def status_text(self) -> str:
        if self.job.running:
            return f"{self.busy_what}…"
        return self.message

    def enabled(self, name: str) -> bool:
        has_item = self.item is not None
        has_rec = self.record is not None
        idle = not self.job.running
        if name in ("approve_item", "reject_item", "reset_item"):
            return has_item and idle
        if name == "approve_all":
            return has_rec and idle and bool(self._approvable())
        if name == "build_record":
            return idle and bool(self.config_name)
        if name == "create_record":
            return idle and not self.new_name_problem.startswith(("Type", "**"))
        if name in ("add_files", "add_folder"):
            return idle and self._can_add()
        if name in ("show_folder", "scan_for_review"):
            return has_rec and idle
        if name.startswith("meta_"):
            return has_rec and idle
        if name == "open_in_ndx":
            return self.ndx_container is not None
        if name in ("rescan", "build_package"):
            return has_rec and idle
        if name == "check_remote":
            return has_rec and idle and bool(self.open_record.remote.get("deposition_id"))
        if name == "upload_draft":
            return has_rec and idle and bool(self.token_source) and not blockers(self.record)
        if name in ("save_token",):
            return idle and bool(self.token_entry.strip())
        if name == "test_token":
            return idle and bool(self.token_source)
        if name == "forget_token":
            return idle and self.token_source == "keychain"
        if name == "approve_publish":
            return has_rec and idle and bool(self.open_record.remote.get("deposition_id")) \
                and not compare(self.record) and not self.open_record.remote.get("doi")
        if name == "publish_record":
            return has_rec and idle and bool(self.token_source) \
                and not blockers(self.record, for_publish=True) \
                and not self.open_record.remote.get("doi")
        return True

    # ── the one line that says what to do next ───────────────────────────
    @property
    def next_step(self) -> str:
        """The single next thing to do, in words -- shown above everything."""
        if self.job.running:
            return f"**Working:** {self.busy_what}… (the window stays usable)"
        if not self.token_source:
            return ("**Step 0 -- enter your Zenodo token** in the *Zenodo token* tab. "
                    "Reviewing works without it; uploading does not.")
        if self.record is None:
            return ("**Step 1 -- pick a record** in the list above, or make a new one in "
                    "*0 · Create*.")
        rec = self.record
        if rec.remote.get("doi"):
            return f"**Done:** {rec.name} is published, DOI {rec.remote['doi']}."
        if not any(i.role in ("measurement", "calibration") for i in rec.items):
            return ("**Step 2 -- add data** (*0 · Create*): name an item, then *Add files…* or "
                    "*Add folder…*.")
        if zenodo_problems(rec.metadata):
            return ("**Step 3 -- complete the Zenodo metadata** (*0 · Create*): "
                    f"{len(zenodo_problems(rec.metadata))} field(s) missing or wrong, listed "
                    "under the form.")
        c = rec.counts()
        open_items = [i for i in rec.items if i.status != "approved"]
        if c["rejected"]:
            return (f"**Fix {c['rejected']} rejected item(s)** in the record folder, then "
                    "*Rescan* (Upload tab) and review them again.")
        if open_items:
            flagged = sum(1 for i in open_items if i.flags)
            return (f"**Step 4 -- review** (*1 · Review*): {len(open_items)} of {len(rec.items)} items still "
                    "to check" + (f", {flagged} of them flagged (Check column) -- start with those" if flagged
                       else "")
                    + ". Approve a row with its button; right-click it to reject.")
        b = blockers(rec)
        if b:
            return ("**Step 5 -- build the package** (Upload tab): everything is approved, the "
                    "archive must be built from exactly this content.")
        if not rec.remote.get("deposition_id"):
            return ("**Step 6 -- upload the draft** (Upload tab). Nothing is published; you can "
                    "still look at the draft on Zenodo afterwards.")
        diff = compare(rec)
        if diff:
            return f"**Check the draft:** {'; '.join(diff)}. Upload again or *Check Zenodo*."
        if rec.publish.status != "approved" or rec.publish.digest != rec.package.get("md5"):
            return ("**Draft uploaded and verified.** Look at it on Zenodo; when it is right, "
                    "*Approve publish*, then *Publish* (irreversible).")
        return "**Ready to publish.** *Publish* is irreversible."

    # ── the Zenodo token ─────────────────────────────────────────────────
    @property
    def _base(self) -> str:
        return SANDBOX if self.sandbox else PRODUCTION

    @property
    def token_source(self) -> str:
        return credentials.load_token(self._base)[1]

    @property
    def token_text(self) -> str:
        where = "sandbox.zenodo.org" if self.sandbox else "zenodo.org"
        src = self.token_source
        state = {"keychain": "stored in the system keychain",
                 "environment": "taken from the ZENODO_TOKEN environment variable",
                 "": "**not set** -- uploading is impossible until you enter one"}[src]
        check = f"\n\nLast test: {self.token_check}" if self.token_check else ""
        return (f"Token for **{where}**: {state}.\n\nCreate one on Zenodo under *Account → "
                "Applications → Personal access tokens* with the scopes **deposit:write** and "
                "**deposit:actions**. It is kept in the system keychain only -- never in a file "
                "or in ChiSurf's settings." + check)

    def save_token(self) -> None:
        tok = self.token_entry.strip()
        self.token_entry = ""
        if not tok:
            self.message = "the token field is empty"
            return
        ok = credentials.store_token(self._base, tok)
        self.message = "token stored in the system keychain" if ok else (
            "no system keychain available: set ZENODO_TOKEN instead")
        self.token_check = ""

    def forget_token(self) -> None:
        credentials.delete_token(self._base)
        self.token_check = ""
        self.message = "stored token removed"

    def test_token(self) -> None:
        try:
            client = self._client()
        except RuntimeError as exc:
            self.token_check = str(exc)
            return
        self.busy_what = "testing the token"

        def work():
            return client.check_token()

        def done(problem):
            self.token_check = problem or "accepted: the token can create depositions"
            self.message = self.token_check

        def fail(exc):
            self.token_check = f"could not reach Zenodo: {exc}"

        self.job.start(work, done, fail)

    # ── why a button is grey ─────────────────────────────────────────────
    @property
    def upload_hint(self) -> str:
        if self.record is None:
            return ""
        if not self.token_source:
            return "Upload needs a token (Zenodo token tab)."
        b = blockers(self.record)
        if b:
            return f"Upload is locked: {len(b)} thing(s) block it -- see the list above."
        return "Upload is unlocked."

    # ── worker steps ─────────────────────────────────────────────────────
    def _run(self, what: str, work) -> None:
        rec = self.record
        self.busy_what = what

        def done(msg):
            rec.save()
            self.message = msg
            self.refresh_records()

        def fail(exc):
            rec.save()
            self.message = (f"{what} refused: " if isinstance(exc, GateError)
                            else f"{what} failed: ") + str(exc)

        self.job.start(work, done, fail)

    def _client(self):
        return self._client_factory(self._base)

    def build_package(self) -> None:
        rec = self.open_record
        out = rec.folder.parent.parent / ZIPS

        def work():
            p = build_package(rec, out)
            return f"package built: {p.name}, md5 {rec.package['md5']}"

        self._run("building the package", work)

    def upload_draft(self) -> None:
        rec, client = self.record, self._client()

        def work():
            remote = upload(rec, client)
            return f"uploaded to draft {remote['deposition_id']}: " + (
                "; ".join(compare(rec)) or "md5 verified")

        self._run("uploading to a Zenodo draft", work)

    def check_remote(self) -> None:
        rec, client = self.record, self._client()

        def work():
            refresh_remote(rec, client)
            return "; ".join(compare(rec)) or "remote matches the package"

        self._run("checking Zenodo", work)

    def approve_publish(self) -> None:
        self.open_record.approve_publish(self.note.strip())
        self.open_record.save()
        self.message = f"publishing approved for md5 {self.open_record.package['md5']}"

    def publish_record(self) -> None:
        rec, client = self.record, self._client()

        def work():
            remote = publish(rec, client)
            return f"published: DOI {remote.get('doi')}"

        self._run("publishing", work)

    def poll(self) -> None:
        self.job.poll()

    # ── persistence ──────────────────────────────────────────────────────
    def export_settings(self) -> dict:
        return {"data_root": self.data_root, "sandbox": self.sandbox,
                "configs_dir": self.configs_dir, "build_command": self.build_command,
                "scan_command": self.scan_command}

    def restore_settings(self, state: dict) -> None:
        self.data_root = str(state.get("data_root") or self.data_root)
        self.configs_dir = str(state.get("configs_dir") or self.configs_dir)
        self.build_command = str(state.get("build_command") or self.build_command)
        self.scan_command = str(state.get("scan_command") or self.scan_command)
        self.sandbox = bool(state.get("sandbox", False))
        self.refresh_records()

    def close(self) -> None:
        self.job.stop()
