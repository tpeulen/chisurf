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
    refresh_remote,
    scan,
    upload,
)

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
            if row["state"] == "not scanned":
                self.record.save()
                self.refresh_records()
        except Exception as exc:  # noqa: BLE001 - shown to the reviewer
            self.record, self.message = None, f"could not open {row['name']}: {exc}"
            return
        self.item_id = ""
        self.message = f"opened {self.record.name}"

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
            return "**No Zenodo metadata** -- the record's build config has no \"zenodo\" block."
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
                 "flags": ("✖ " if i.errors else "") + (f"⚠ {len(i.flags)}" if i.flags else ""),
                 "detail": "\n".join(i.flags) or i.description}
                for i in self.record.items]

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
        """What the reviewer needs to judge the selected item."""
        it = self.item
        if it is None:
            return "Select an item to see where it came from, what it holds and why it is flagged."
        lines = [f"### {it.id}", ""]
        if it.errors:
            lines += [f"**Fails the machine check ({len(it.errors)}) -- blocks the upload:**", ""] \
                + [f"- {_md(e)}" for e in it.errors[:12]] + [""]
        if it.flags:
            lines += ["**Needs your check:**", ""] + [f"- {_md(f)}" for f in it.flags] + [""]
        if it.description:
            lines += [f"**Content:** {_md(it.description)}", ""]
        if it.origin:
            lines += [f"**Original location:** {_md(it.origin)}", ""]
        holds = f"{it.files} file{'s' if it.files != 1 else ''}, {_size(it.bytes)}"
        if self.ndx_container:
            holds += f" -- burst analysis: {self.ndx_container.name} (Open in ndX)"
        lines += [f"**Holds:** {holds}", ""]
        r = it.review
        if r.status != "pending" or r.by:
            lines += [f"**Review:** {r.status} by {_md(r.by)} at {r.at}"
                      + (f" -- {_md(r.note)}" if r.note else "")
                      + (" -- content changed since" if it.status != r.status else "")]
        return "\n".join(lines)

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
        if it is None:
            return None
        p = self.open_record.folder / it.id
        if p.is_file():
            return p if p.name.endswith(".pto") else None
        return next(iter(sorted(p.glob("*.mmfdb.pto"))), None) if p.is_dir() else None

    def open_in_ndx(self) -> None:
        """Open the selected item's container in ndX, to look at the bursts before approving."""
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
    def preview_md(self) -> str:
        return self.preview_text if self.preview_kind == "markdown" else ""

    @property
    def preview_txt(self) -> str:
        return self.preview_text if self.preview_kind in ("text", "listing") else ""

    # ── review ───────────────────────────────────────────────────────────
    def _review(self, status: str) -> None:
        if self.record is None or self.item is None:
            return
        self.record.set_review(self.item_id, status, self.note.strip())
        self.record.save()
        self.message = f"{status}: {self.item_id}"
        self.note = ""
        self.refresh_records()

    def approve_item(self) -> None:
        self._review("approved")

    def reject_item(self) -> None:
        self._review("rejected")

    def reset_item(self) -> None:
        self._review("pending")

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
        if name == "build_record":
            return idle and bool(self.config_name)
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
            return ("**Step 1 -- pick a record** in the list above (or build one first in "
                    "*0 · Create*).")
        rec = self.record
        if rec.remote.get("doi"):
            return f"**Done:** {rec.name} is published, DOI {rec.remote['doi']}."
        c = rec.counts()
        open_items = [i for i in rec.items if i.status != "approved"]
        if c["rejected"]:
            return (f"**Fix {c['rejected']} rejected item(s)** in the record folder, then "
                    "*Rescan* (Upload tab) and review them again.")
        if open_items:
            flagged = sum(1 for i in open_items if i.flags)
            return (f"**Step 2 -- review:** {len(open_items)} of {len(rec.items)} items still "
                    "to check" + (f", {flagged} of them flagged (Check column) -- start with those" if flagged
                       else "")
                    + ". Click a row, read it, then Approve or Reject.")
        b = blockers(rec)
        if b:
            return ("**Step 3 -- build the package** (Upload tab): everything is approved, the "
                    "archive must be built from exactly this content.")
        if not rec.remote.get("deposition_id"):
            return ("**Step 4 -- upload the draft** (Upload tab). Nothing is published; you can "
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
