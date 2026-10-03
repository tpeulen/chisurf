"""Qt-free state and actions for the staging spectra workflows."""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from chisurf.plugins.core.mmfdb_admin.gui.session import (
    active_user_id,
    cache_session,
    cached_token,
    client_is_admin,
    local_admin_status,
)

from ..download._base import SCRAPERS, get_scraper


class SpectraState:
    def __init__(self, db):
        self.db = db
        self.rows = []
        self.search = self.category = self.source = ""
        self.selected = set()
        self.detail = None
        self.log = ""
        self.mmfdb_log = ""
        self.process = None
        self.messages = queue.SimpleQueue()
        self.module = sorted(SCRAPERS, key=lambda s: s.label)[0].module
        from mmfdb.store.database_resolver import resolve_database_path

        self.endpoint = SimpleNamespace(
            mode="local",
            db_path=str(resolve_database_path()),
            host="127.0.0.1",
            cmd_port=8765,
            pub_port=8766,
            user=active_user_id(),
            password="",
            replace=False,
            mark_verified=False,
        )
        self.refresh()

    def refresh(self):
        op = "(SELECT property_value FROM optical_properties o WHERE o.probe_id=p.probe_id AND o.property_name=? AND o.deleted_at IS NULL LIMIT 1)"
        self.rows = [
            dict(r)
            for r in self.db.conn.execute(
                f"SELECT p.*, {op} AS abs_max, {op} AS em_max, {op} AS qy, {op} AS ext_coeff, {op} AS lifetime, t.display_name AS type_name FROM probes p LEFT JOIN probe_types t ON t.type_id=p.type_id WHERE p.deleted_at IS NULL ORDER BY p.chromophore_name",
                ["abs_max", "em_max", "qy", "ext_coeff", "lifetime"],
            )
        ]
        self.selected.intersection_update(r["probe_id"] for r in self.rows)
        if self.detail and self.detail["probe"].get("probe_id") not in self.selected:
            self.detail = None

    @property
    def categories(self):
        return sorted({r["category"] for r in self.rows if r.get("category")})

    @property
    def sources(self):
        return sorted(
            {
                t.strip()
                for r in self.rows
                for t in str(r.get("source") or "").split(",")
                if t.strip()
            }
        )

    def filtered(self):
        return [
            r
            for r in self.rows
            if (not self.category or r.get("category") == self.category)
            and (
                not self.source
                or self.source in {t.strip() for t in str(r.get("source") or "").split(",")}
            )
            and self.search.strip().lower() in str(r.get("chromophore_name") or "").lower()
        ]

    def overview(self):
        by_cat = {
            r[0] or "": r[1]
            for r in self.db.conn.execute(
                "SELECT category, COUNT(*) FROM probes WHERE deleted_at IS NULL GROUP BY category"
            )
        }
        by_source = {
            r[0] or "": r[1]
            for r in self.db.conn.execute(
                "SELECT source, COUNT(*) FROM probes WHERE deleted_at IS NULL GROUP BY source ORDER BY COUNT(*) DESC"
            )
        }
        return {
            "db_path": str(self.db.db_path),
            "total": sum(by_cat.values()),
            "with_spectra": self.db.conn.execute(
                "SELECT COUNT(DISTINCT probe_id) FROM spectra WHERE deleted_at IS NULL"
            ).fetchone()[0],
            "fluorophores": sum(
                v
                for k, v in by_cat.items()
                if k in {"fluorophore", "organic_dye", "protein", "quantum_dot", "nanoparticle"}
            ),
            **{
                k: by_cat.get(c, 0)
                for k, c in [
                    ("filters", "filter"),
                    ("dichroics", "dichroic"),
                    ("detectors", "detector"),
                    ("light_sources", "light_source"),
                ]
            },
            "by_category": by_cat,
            "by_source": by_source,
        }

    def select(self, probe_id, enabled=True):
        if enabled:
            self.selected.add(probe_id)
            probe = self.db.conn.execute(
                "SELECT * FROM probes WHERE probe_id=? AND deleted_at IS NULL", (probe_id,)
            ).fetchone()
            props = self.db.conn.execute(
                "SELECT property_name, property_value FROM optical_properties WHERE probe_id=? AND deleted_at IS NULL ORDER BY property_name",
                (probe_id,),
            )
            spectra = self.db.conn.execute(
                "SELECT * FROM spectra WHERE probe_id=? AND deleted_at IS NULL", (probe_id,)
            )
            self.detail = {
                "probe": dict(probe) if probe else {},
                "optical_properties": [dict(r) for r in props],
                "spectra": [
                    {
                        "spectrum_type": r["spectrum_type"],
                        "wavelengths": np.frombuffer(r["wavelengths"], dtype=np.float64).tolist(),
                        "intensity": np.frombuffer(
                            r["intensity_values"], dtype=np.float64
                        ).tolist(),
                    }
                    for r in spectra
                ],
            }
        else:
            self.selected.discard(probe_id)
            if self.detail and self.detail["probe"].get("probe_id") == probe_id:
                self.detail = None

    def show(self, probe_id):
        """Load *probe_id* into the detail (the clicked row), without changing which rows are picked for a push."""
        was = probe_id in self.selected
        self.select(probe_id)
        if not was:
            self.selected.discard(probe_id)

    def pick(self, probe_id, enabled=True):
        """Pick (or un-pick) a component for ``Push selected``; the detail keeps showing the last clicked row."""
        if enabled:
            self.selected.add(probe_id)
        else:
            self.selected.discard(probe_id)

    def push(self, selected=False):
        from ..download.merge import push_staging_to_mmfdb

        if selected and not self.selected:
            raise ValueError("No components selected.")
        return push_staging_to_mmfdb(
            str(self.db.db_path), probe_ids=sorted(self.selected) if selected else None
        )

    def source_slug(self):
        spec = get_scraper(self.module)
        return spec.source if spec else self.module

    def source_counts(self):
        slug = self.source_slug()
        return dict(
            self.db.conn.execute(
                "SELECT category, COUNT(*) n FROM probes WHERE deleted_at IS NULL AND (',' || IFNULL(source,'') || ',') LIKE ? GROUP BY category ORDER BY n DESC",
                (f"%,{slug},%",),
            )
        )

    def command(self):
        return [
            sys.executable,
            "-m",
            f"chisurf.plugins.spectra_downloader.download.{self.module}",
            "--db",
            str(self.db.db_path),
        ]

    def run_script(self):
        if self.process is not None:
            return False
        self.log = f"--- Running {self.module} ---\n"
        self.process = subprocess.Popen(
            self.command(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf8",
            errors="replace",
        )
        process = self.process

        def read():
            for line in process.stdout:
                self.messages.put(("output", line))
            self.messages.put(("finished", process.wait()))

        threading.Thread(target=read, daemon=True).start()
        return True

    def poll(self):
        while not self.messages.empty():
            kind, value = self.messages.get()
            if kind == "output":
                self.log += value
            else:
                self.log += f"--- Finished ({value}) ---\n"
                self.process = None
                self.refresh()

    def server_client(self):
        from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

        m = self.endpoint
        client = MMFDBClient(host=m.host, cmd_port=int(m.cmd_port), pub_port=int(m.pub_port))
        token = cached_token(m.host, m.cmd_port, m.pub_port)
        if token:
            client.token = token
        else:
            try:
                result = client.login(m.user or active_user_id(), m.password or "")
            except Exception:
                result = client.login(m.user or active_user_id(), m.password) if m.password else {}
            if isinstance(result, dict) and result.get("ok"):
                cache_session(
                    m.user or active_user_id(), client.token, m.host, m.cmd_port, m.pub_port
                )
        return client

    def authorized(self):
        m = self.endpoint
        user = m.user or active_user_id()
        if m.mode == "server":
            try:
                return client_is_admin(self.server_client(), user), f"{m.host}:{m.cmd_port}"
            except Exception as exc:
                return False, str(exc)
        target = m.db_path or self.resolved()
        admin, any_admin = (
            local_admin_status(target, user) if Path(target).exists() else (True, False)
        )
        return admin, Path(target).name if any_admin else "bootstrap"

    @staticmethod
    def resolved():
        from mmfdb.store.database_resolver import resolve_database_path

        return str(resolve_database_path())

    def echo(self, message):
        self.mmfdb_log += message + "\n"

    def session_text(self):
        """The Add-to-MMFDB header line, worded as the Qt panel did: ``(admin, text)``."""
        ok, note = self.authorized()
        user = self.endpoint.user or active_user_id()
        if ok:
            return True, f"Session user {user} is an administrator ({note}) - no login needed."
        return False, (
            f"Session user {user} may not add to the MMFDB ({note}). "
            "Set credentials under Advanced or use an admin account."
        )

    def add_all(self):
        m = self.endpoint
        user = m.user or active_user_id()
        if m.mode == "server":
            client = self.server_client()
            if not client_is_admin(client, user):
                raise PermissionError(f"User '{user}' is not an MMFDB administrator.")
            return client._call(
                "fluorophores.import_reference_set",
                {
                    "source_path": str(self.db.db_path),
                    "replace": bool(m.replace),
                    "mark_verified": bool(m.mark_verified),
                },
            )
        from mmfdb.repository import MFDatabase

        target = m.db_path or self.resolved()
        if not local_admin_status(target, user)[0]:
            raise PermissionError(f"User '{user}' is not an administrator of {target}.")
        if m.replace and Path(target).exists():
            shutil.copy2(target, f"{target}.bak")
        with MFDatabase(target) as db:
            return db.import_reference_set(
                source_path=str(self.db.db_path),
                replace=bool(m.replace),
                mark_verified=bool(m.mark_verified),
            )

    def add_all_logged(self):
        """:meth:`add_all` worded into :attr:`mmfdb_log` as the Qt panel's log was; ``None`` when it did not add."""
        m = self.endpoint
        user = m.user or active_user_id()
        where = f"server {m.host}:{m.cmd_port}" if m.mode == "server" else f"local MMFDB {m.db_path or self.resolved()}"
        self.echo(f"Adding to {where} as '{user}' (replace={m.replace}) ...")
        try:
            result = self.add_all()
        except PermissionError as exc:
            self.echo(f"{exc} Cannot add.")
            return None
        except Exception as exc:  # noqa: BLE001 - reported in the log like the Qt panel
            self.echo(f"Add failed: {exc}")
            return None
        if isinstance(result, dict) and "probes" in result and "spectra" in result:
            self.echo(
                f"Done: probes={result['probes']} spectra={result['spectra']} props={result.get('optical_properties')} "
                f"consolidated={result.get('consolidated')}" + (f" purged={result['purged']}" if result.get("purged") else "")
            )
        else:
            self.echo(f"Done: {result}")
        return result

    def close(self):
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
            self.process.stdout.close()
            self.process = None
