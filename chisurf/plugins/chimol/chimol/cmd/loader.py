from __future__ import annotations

import re
import shutil
import ssl
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from .base import BaseCmd
from .registry import command


def _download_dir() -> Path:
    """Return the directory where fetched entries are kept.

    A real cache directory, not the shared temp dir. ``fetch`` re-uses what it
    has already downloaded, and a *scratch* path is the wrong place to do that:
    the name is guessable, anything may write it, and a leftover from an
    unrelated program or an interrupted download would be handed to the reader
    as though it were the entry. Under the user's own ``.chisurf`` it is a cache
    they own and can clear.

    Returns
    -------
    pathlib.Path
        The directory, created if it does not exist. Falls back to the temp
        directory when the home directory cannot be written.
    """
    try:
        directory = Path.home() / ".chisurf" / "structures" / "chimol"
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    except Exception:  # pragma: no cover - unwritable home
        return Path(tempfile.gettempdir())


def _tls_context() -> ssl.SSLContext | None:
    """Build a verifying TLS context that ignores the ambient CA store.

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

    @command("load_traj")
    def load_traj(self, path: str = "", obj: str = "") -> None:
        """Read coordinate frames onto an object that already has atoms.

        PyMOL's ``load_traj file [, object]``, and the only way to open a DCD or
        an XTC usefully: they store coordinates and *nothing else* -- no atom
        names, no residues, no chains. Loaded on their own they arrive as a bare
        point cloud, and everything keyed on atom identity degrades without
        erroring: the cartoon splines through every atom instead of the CA
        trace, a selection resolves to nothing, the sequence view is empty.

        So the topology comes from a structure file loaded first, and the frames
        are laid onto it here -- the same split the trajectory tools make with
        their topology picker.

        Parameters
        ----------
        path : str
            The trajectory. See :data:`~chisurf.plugins.chimol.chimol.io.structure.TRAJECTORY_SUFFIXES`.
        obj : str, optional
            Which object to lay the frames onto. Defaults to the active one.
        """
        if not str(path).strip():
            self._emit_error("Usage: load_traj <path> [, object]")
            return

        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        from ..io.structure import TrajectoryFormatError, load_trajectory_frames

        resolved = Path(str(path).strip()).expanduser()
        try:
            frames = load_trajectory_frames(resolved)
        except TrajectoryFormatError as exc:
            self._emit_error(f"load_traj: {exc}")
            return
        except Exception as exc:
            self._emit_error(f"load_traj: could not read '{resolved}': {exc}")
            return

        obj_id = str(obj).strip() or None
        if obj_id is not None:
            obj_id = self._object_id_for_name(viewer, obj_id)
            if obj_id is None:
                self._emit_error(f"load_traj: there is no object named '{obj}'")
                return
        else:
            obj_id = viewer.get_active_object_id()
        if obj_id is None:
            self._emit_error(
                "load_traj: nothing is loaded to lay the frames onto -- load the "
                "structure that names the atoms first"
            )
            return

        # The atom counts must agree, and this is the check worth having: a
        # mismatch is silent otherwise. The frames simply replace the
        # coordinates, so a topology with a different number of atoms relabels
        # every position with the wrong atom's name and draws a plausible,
        # entirely wrong molecule.
        entry = viewer._objects.get(obj_id)
        obj_name = getattr(entry, "name", str(obj_id))
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is not None and len(atoms) != int(frames.shape[1]):
            self._emit_error(
                f"load_traj: '{resolved.name}' has {frames.shape[1]} atoms per "
                f"frame but {obj_name} has {len(atoms)}; they are not the same "
                "molecule"
            )
            return

        try:
            viewer.set_frames(frames, object_id=obj_id)
        except Exception as exc:
            self._emit_error(f"load_traj: could not store the frames: {exc}")
            return
        self._emit_message(
            f"load_traj: {frames.shape[0]} states of {frames.shape[1]} atoms "
            f"onto {obj_name}"
        )

    @staticmethod
    def _object_id_for_name(viewer, name: str) -> str | None:
        """Return the id of the object called ``name``, or ``None``."""
        for object_id, entry in getattr(viewer, "_objects", {}).items():
            if str(getattr(entry, "name", object_id)) == name:
                return object_id
        return name if name in getattr(viewer, "_objects", {}) else None

    #: The repositories `fetch` knows. One table rather than three near-identical
    #: commands: the three that were here had drifted, and one of them had never
    #: worked at all.
    #:
    #: **Order matters, and ``pdb`` must come last.** Its pattern is the loosest
    #: -- any four characters -- so anything ahead of it in this table is only
    #: reachable if it is tried first. PDB-IHM used to sit *after* ``pdb`` with
    #: the pattern ``^\d[0-9a-z]{3}$``, which is a strict subset of "any four
    #: characters": unreachable, and wrong even if reached, since `148l` and
    #: `8zzc` are ordinary PDB codes that happen to start with a digit.
    REPOSITORIES = {
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
            #: ``PDBDEV_00000012`` is the canonical form -- it is what the entry
            #: is called on the site, in our own demo and in the guide -- and it
            #: matched nothing here, so `fetch PDBDEV_00000012` asked RCSB for a
            #: PDB entry and reported a PDB failure. The short ``ihm-12`` spelling
            #: is kept because it was already accepted.
            "pattern": r"^pdbdev[-_]?\d+$|^ihm[-_]?\d+$",
        },
        "pdb": {
            "label": "RCSB PDB",
            "url": "https://files.rcsb.org/download/{id}.pdb",
            "suffix": ".pdb",
            "normalise": str.lower,
            #: 4-character PDB codes, and the newer extended ones. Deliberately
            #: last: this is the catch-all.
            "pattern": r"^[0-9a-z]{4}$|^pdb_[0-9a-z]{8}$",
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
        """Which repository an identifier looks like it belongs to.

        First match wins, so :data:`REPOSITORIES` is ordered specific-first with
        ``pdb`` last -- see the note there.

        Parameters
        ----------
        code : str
            The identifier as typed.

        Returns
        -------
        str
            A key of :data:`REPOSITORIES`; ``"pdb"`` when nothing matches, since
            a bare code is a PDB code far more often than anything else.
        """
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
            _download_dir()
            / f"chimol_{name.replace('-', '_')}_{identifier}{spec['suffix']}"
        )
        # Re-use a copy already downloaded. `fetch` is what the demos and the
        # docs tell people to type, and the eight-spoke nuclear pore is 31.5 MB:
        # fetching it again on every run costs the download and gains nothing,
        # since an entry at a given accession does not change under you.
        if destination.is_file() and destination.stat().st_size > 0:
            try:
                window._load_structure_from_path(destination, name=display)
            except Exception as exc:
                self._emit_error(
                    f"fetch: the cached {display} would not load ({exc}); "
                    "delete it and try again."
                )
                return
            self._emit_message(f"fetch: loaded {display} (cached)")
            return

        # Downloaded beside the destination and moved into place only once it is
        # complete. Writing straight to the cache path left a **zero-byte file**
        # behind whenever a download failed part-way -- in the user's own cache
        # directory, where the next run would find it sitting where the entry
        # should be. A cache that can contain half an entry is worse than no
        # cache.
        partial = destination.with_name(destination.name + ".part")
        try:
            with urllib.request.urlopen(
                url, timeout=60, context=_tls_context()
            ) as response, partial.open("wb") as fh:
                shutil.copyfileobj(response, fh)
            partial.replace(destination)
        except urllib.error.HTTPError as exc:
            partial.unlink(missing_ok=True)
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
            partial.unlink(missing_ok=True)
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
            partial.unlink(missing_ok=True)
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
