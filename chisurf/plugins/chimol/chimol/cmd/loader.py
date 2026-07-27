from __future__ import annotations

import re
import ssl
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from .base import BaseCmd
from .registry import command


def _tls_context() -> ssl.SSLContext | None:
    """A verifying TLS context that does not depend on the ambient CA store.

    ``urlopen`` with no context trusts whatever OpenSSL was compiled to look at,
    which on a machine running the app from a packaged or framework interpreter
    is routinely a path with no certificates in it -- and then every ``fetch``
    fails with ``CERTIFICATE_VERIFY_FAILED`` while the same URL downloads fine
    in a browser. ``certifi`` ships the bundle the rest of the Python ecosystem
    verifies against, so use it when it is installed.

    Returns
    -------
    ssl.SSLContext or None
        A context built from certifi's bundle, or ``None`` to let ``urlopen``
        use its default when certifi is unavailable. Verification is never
        turned off: a fetch that cannot be verified is a fetch that fails.
    """
    try:
        import certifi
    except Exception:  # pragma: no cover - certifi is a normal dependency
        return None
    try:
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # pragma: no cover - unreadable bundle
        return None


class LoaderCommands(BaseCmd):
    """Loading and remote fetch commands."""

    @command("load", aliases=("open",))
    def load(self, *paths: str) -> None:
        """Load one or more structure files (PyMOL ``load path[, ...]``)."""
        args = list(paths)
        if not args:
            self._emit_error("Usage: load <path> [more paths...]")
            return

        window = self.window
        if window is None:
            self._emit_error("No viewer window is attached")
            return

        for raw in args:
            path = Path(raw).expanduser()
            # A session replaces the whole viewer rather than adding an object,
            # so it cannot go through the structure reader.
            if self.names_a_session(path):
                self.session_load(str(path))
                continue
            try:
                window._load_structure_from_path(path)
            except Exception as exc:
                self._emit_error(f"Failed to load '{path}': {exc}")
            else:
                self._emit_message(f"Loaded: {path}")

    #: The repositories `fetch` knows, in the order an unlabelled id is tried
    #: against them. One table rather than three near-identical commands: the
    #: three that were here had drifted, and one of them had never worked at all.
    REPOSITORIES = {
        "pdb": {
            "label": "RCSB PDB",
            "url": "https://files.rcsb.org/download/{id}.pdb",
            "suffix": ".pdb",
            "normalise": str.lower,
            #: 4-character PDB codes, and the newer extended ones.
            "pattern": r"^[0-9a-z]{4}$|^pdb_[0-9a-z]{8}$",
        },
        "emdb": {
            "label": "EMDB",
            "url": (
                "https://ftp.ebi.ac.uk/pub/databases/emdb/structures/"
                "EMD-{num}/map/emd_{num}.map.gz"
            ),
            "suffix": ".map.gz",
            "normalise": str.upper,
            "pattern": r"^emd[-_]?\d{4,5}$",
        },
        "pdb-ihm": {
            "label": "PDB-IHM",
            "url": "https://pdb-ihm.org/cif/{id}.cif",
            "suffix": ".cif",
            "normalise": str.lower,
            "pattern": r"^\d[0-9a-z]{3}$|^ihm[-_]?\d+$",
        },
    }

    @command("fetch")
    def fetch(self, *ids: str) -> None:
        """Fetch entries from the PDB, EMDB or PDB-IHM (PyMOL ``fetch id[, ...]``).

        The repository is recognised from the identifier, so ``fetch 148l`` gets
        a structure and ``fetch EMD-1234`` gets a density map. Naming one
        explicitly still works::

            fetch 148l
            fetch EMD-3061
            fetch 8zzz, pdb-ihm

        An EMDB map arrives as a **map object** with a contour on it, not as a
        structure -- see the Map panel.
        """
        args = [str(value).strip() for value in ids if str(value).strip()]
        if not args:
            self._emit_error(
                "Usage: fetch <id> [more ids...] [, repository]  "
                f"(repositories: {', '.join(self.REPOSITORIES)})"
            )
            return

        # A trailing token naming a repository applies to everything before it.
        forced = None
        if len(args) > 1 and args[-1].lower() in self.REPOSITORIES:
            forced = args.pop().lower()

        for code in args:
            self._fetch_one(code, forced)

    @command("fetch_emdb")
    def fetch_emdb(self, *emdb_ids: str) -> None:
        """Fetch EMDB density maps (``fetch_emdb id[, ...]``)."""
        for code in [str(v).strip() for v in emdb_ids if str(v).strip()]:
            self._fetch_one(code, "emdb")

    @command("fetch_ihm")
    def fetch_ihm(self, *entry_ids: str) -> None:
        """Fetch integrative-model structures from PDB-IHM."""
        for code in [str(v).strip() for v in entry_ids if str(v).strip()]:
            self._fetch_one(code, "pdb-ihm")

    def _repository_for(self, code: str) -> str:
        """Which repository an identifier looks like it belongs to."""
        lowered = code.lower()
        for name, spec in self.REPOSITORIES.items():
            if re.match(spec["pattern"], lowered):
                return name
        return "pdb"

    def _fetch_one(self, code: str, repository: str | None = None) -> None:
        """Download one entry and load it, reporting what went wrong if it did."""
        window = self.window
        if window is None:
            self._emit_error("No viewer window is attached")
            return

        name = repository or self._repository_for(code)
        spec = self.REPOSITORIES.get(name)
        if spec is None:
            self._emit_error(
                f"fetch: unknown repository {name!r}; "
                f"known: {', '.join(self.REPOSITORIES)}"
            )
            return

        identifier = spec["normalise"](code)
        digits = re.search(r"\d+", code)
        if name == "emdb":
            if digits is None:
                self._emit_error(
                    f"fetch: could not read an EMDB number from {code!r} "
                    "(expected something like EMD-3061)"
                )
                return
            url = spec["url"].format(num=digits.group(0), id=identifier)
            display = f"EMD-{digits.group(0)}"
        else:
            url = spec["url"].format(id=identifier, num=digits.group(0) if digits else "")
            display = identifier

        destination = (
            Path(tempfile.gettempdir())
            / f"chimol_{name.replace('-', '_')}_{identifier}{spec['suffix']}"
        )
        try:
            with urllib.request.urlopen(
                url, timeout=60, context=_tls_context()
            ) as response, destination.open("wb") as fh:
                fh.write(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                self._emit_error(
                    f"fetch: {spec['label']} has no entry {display}"
                )
            else:
                self._emit_error(
                    f"fetch: {spec['label']} returned {exc.code} for {display}"
                )
            return
        except urllib.error.URLError as exc:
            # A certificate failure is not a missing entry and not a network
            # outage, and the raw OpenSSL string says so to nobody. Name it.
            reason = exc.reason
            if isinstance(reason, ssl.SSLError):
                self._emit_error(
                    f"fetch: could not verify {spec['label']}'s certificate. "
                    "This Python has no usable CA bundle -- installing "
                    "'certifi' in the environment running ChiSurf fixes it."
                )
            else:
                self._emit_error(
                    f"fetch: could not reach {spec['label']} for {display}: {reason}"
                )
            return
        except Exception as exc:
            self._emit_error(
                f"fetch: could not get {display} from {spec['label']}: {exc}"
            )
            return

        try:
            window._load_structure_from_path(destination, name=display)
        except Exception as exc:
            self._emit_error(f"fetch: {display} downloaded but would not load: {exc}")
            return
        self._emit_message(f"fetch: loaded {display} from {spec['label']}")
