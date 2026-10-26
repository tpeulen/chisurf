"""What a dropped path is: the one place the workspace decides how a file enters it.

The shell has one way in — a file drop (``okf/specs/data-workspace.md``) — and every dropped path is
sorted here by what it holds, not by which reader happens to be selected:

* ``"project"`` — a ChiSurf project (``.cs.pto``): opened, not imported;
* ``"container"`` — a measurement container (``.pto``): its photon streams and its burst runs
  become workspace datasets (:func:`container_entries`);
* ``"photons"`` — a vendor photon file (PTU, HT3, SPC, …): one photon dataset;
* ``"image"`` also for a vendor photon file whose header describes an image (a scanning confocal
  recording, ``ImgHdr_*`` tags): a photon image (:func:`is_photon_image`);
* ``"structure"`` — a molecular structure (PDB, mmCIF);
* ``"image"`` — an intensity image stack (TIFF);
* ``"setup"`` — what a tool reads besides the measurement: a look-up table, or a JSON file that is a
  detector/channel setup, a kinetic scheme or an IRF/background pattern (:data:`SETUP_JSON_KEYS`);
* ``"companion"`` — a file that only exists beside a primary one (an SPC's ``.set``): taken with
  its primary, never on its own;
* ``"burst_folder"`` — a legacy burstwise analysis folder (``bi4_bur/*.bur``): handed to
  burstwise import, which brings its runs into the project's analysis containers.
* ``"curve"`` — anything else: read by the selected reader, as before.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "IMAGE_EXTENSIONS",
    "SETUP_EXTENSIONS",
    "SETUP_JSON_KEYS",
    "STRUCTURE_EXTENSIONS",
    "BURST_RUN_OPERATIONS",
    "classify",
    "container_entries",
    "is_burst_folder",
    "curve_reader",
    "is_photon_image",
]

#: Molecular structures a workspace drop reads as a structure.
STRUCTURE_EXTENSIONS: tuple[str, ...] = (".pdb", ".ent", ".cif", ".mmcif", ".pdb.gz", ".cif.gz")

#: Image stacks a workspace drop links as an image.
IMAGE_EXTENSIONS: tuple[str, ...] = (".tif", ".tiff")

#: Look-up tables and patterns a workspace drop links as a setup.
SETUP_EXTENSIONS: tuple[str, ...] = (".lut", ".npz", ".npy")

#: Top-level keys that make a JSON file a setup a tool reads (a detector/channel setup, a kinetic
#: scheme, an IRF or background pattern) rather than something else (a project, a curve export).
SETUP_JSON_KEYS: frozenset[str] = frozenset(
    {"detectors", "channels", "routing", "windows", "setups", "rate_matrix", "scheme", "states",
     "transitions", "irf", "background", "patterns", "lut", "luts", "shifts"}
)

#: The ``schema`` prefix of an acquisition settings file (the Record tool's settings document).
ACQUISITION_SCHEMA_PREFIX = "chisurf.acquisition/"


#: Operations whose burst-grain ``<run>/bursts`` table is a burst run of the workspace: the
#: search itself (a fusion of a search is stored as one), and an imported burst selection (BID).
BURST_RUN_OPERATIONS: frozenset[str] = frozenset({"burst_selection", "import"})

#: Photon formats whose header can name an image: PicoQuant's tagged files.
PHOTON_IMAGE_EXTENSIONS: tuple[str, ...] = (".ptu", ".phu")

#: How much of a tagged file's start is searched for its image tags (its header is far smaller).
_HEADER_PROBE_BYTES = 1 << 20


def is_photon_image(path: str | Path) -> bool:
    """Whether the photon file at *path* records an image (a scanning confocal recording).

    Pure Python and header only, so probing a file can never take the process down: a PicoQuant
    tagged file names its image in ``ImgHdr_*`` tags inside its header, which is searched as bytes
    (the start of the file, :data:`_HEADER_PROBE_BYTES`). Any other format, or a file that cannot be
    read, is not an image.
    """
    path = Path(path)
    if _suffix(path) not in PHOTON_IMAGE_EXTENSIONS:
        return False
    try:
        with open(path, "rb") as fh:
            head = fh.read(_HEADER_PROBE_BYTES)
    except OSError:
        return False
    return head[:6] in (b"PQTTTR", b"PQHIST") and b"ImgHdr_" in head


def _is_setup_json(path: Path) -> bool:
    """Whether the JSON file at *path* is a setup (its top level names one of :data:`SETUP_JSON_KEYS`)."""
    import json

    try:
        if path.stat().st_size > 16 * 2**20:
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    # An acquisition settings file (device, laser, experiment, run) is read by the Record tool.
    return bool(SETUP_JSON_KEYS & set(data)) or str(data.get("schema", "")).startswith(
        ACQUISITION_SCHEMA_PREFIX
    )


def _suffix(path: Path) -> str:
    name = path.name.lower()
    for compound in (".cs.pto", ".pdb.gz", ".cif.gz"):
        if name.endswith(compound):
            return compound
    return path.suffix.lower()


def is_burst_folder(path: str | Path) -> bool:
    """Whether *path* is a legacy burstwise analysis folder: one holding ``.bur`` burst tables
    (in ``bi4_bur/``, ``bur/`` or itself, the layouts the old burst search wrote)."""
    folder = Path(path)
    if not folder.is_dir():
        return False
    return any(
        next(candidate.glob("*.bur"), None) is not None
        for candidate in (folder / "bi4_bur", folder / "bur", folder)
        if candidate.is_dir()
    )


def classify(path: str | Path) -> str:
    """Return what *path* holds — one of the kinds in the module docstring."""
    from chisurf.core.fio.pto import SIDECAR_ONLY_EXTENSIONS
    from chisurf.core.fio.staging import VENDOR_EXTENSIONS
    from chisurf.core.project.pto import PROJECT_SUFFIX

    if is_burst_folder(path):
        return "burst_folder"
    suffix = _suffix(Path(path))
    if suffix == PROJECT_SUFFIX:
        return "project"
    if suffix == ".pto":
        return "container"
    if suffix in SIDECAR_ONLY_EXTENSIONS:
        return "companion"
    if suffix in VENDOR_EXTENSIONS:
        return "image" if is_photon_image(path) else "photons"
    if suffix in STRUCTURE_EXTENSIONS:
        return "structure"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in SETUP_EXTENSIONS or (suffix == ".json" and _is_setup_json(Path(path))):
        return "setup"
    return "curve"


#: Curve files a correlator writes, by extension: ``(experiment, reader)``.
CURVE_READERS_BY_EXTENSION: dict[str, tuple[str, str]] = {
    ".asc": ("FCS", "ALV-Correlator"),
    ".sin": ("FCS", "Correlator.com SIN"),
    ".fcs": ("FCS", "Zeiss Confocor3"),
    ".cor": ("FCS", "Seidel Kristine"),
    ".sdt": ("TCSPC", "Becker-SDT"),
}
_CURVE_PROBE_BYTES = 1 << 16


def _text_head(path: Path) -> tuple[list[list[float]], int, dict[str, float]]:
    """A text curve's head: its numeric rows, the lines before the first one, and ``# #key: v``
    footer/header values (``dt``, ``l1``, ``l2``, ...)."""
    with open(path, "rb") as fh:
        head = fh.read(_CURVE_PROBE_BYTES)
    with open(path, "rb") as fh:  # the footer (an lltf/VV-VH file keeps dt, l1, l2 there)
        fh.seek(max(0, path.stat().st_size - 4096))
        tail = fh.read()
    lines = head.decode("utf-8", errors="replace").splitlines()
    if len(head) == _CURVE_PROBE_BYTES:
        lines = lines[:-1]  # the last line may be cut
    rows: list[list[float]] = []
    leading = 0
    for line in lines:
        fields = line.replace(",", " ").replace(";", " ").split()
        try:
            row = [float(f) for f in fields] if fields else []
        except ValueError:
            row = []
        if not row or line.lstrip().startswith(("#", "%", "!")):
            if not rows:
                leading += 1
            continue
        rows.append(row)
    meta: dict[str, float] = {}
    for line in (*lines[:leading], *tail.decode("utf-8", errors="replace").splitlines()[-20:]):
        text = line.lstrip("#% !").strip()
        if ":" in text:
            key, _, value = text.partition(":")
            try:
                meta[key.strip().lstrip("#").strip().lower()] = float(value)
            except ValueError:
                pass
    return rows, leading, meta


def curve_reader(path: str | Path) -> tuple[str, str, dict] | None:
    """The experiment, file type and reader settings that read the curve file *path*.

    By the extension a correlator writes, else by the text: a first column of lag times spread
    geometrically over decades is a correlation (FCS); a linear time axis, or a single column of
    counts, is a decay (TCSPC). For a TCSPC text the settings say what the file shows: the lines
    before the data (``skiprows``), whether a time column is there (``x_on``), a ``dt`` and a
    stacked VV/VH channel pair (``is_vv_vh``) its ``# #dt`` / ``# #l1`` lines name. Reads the
    first 64 KiB and the last 4 KiB, never raises; ``None`` when the file says nothing.
    """
    path = Path(path)
    known = CURVE_READERS_BY_EXTENSION.get(_suffix(path))
    if known:
        return (*known, {})
    try:
        rows, leading, meta = _text_head(path)
    except OSError:
        return None
    if len(rows) < 8:
        return None
    x = [r[0] for r in rows]
    steps = [b - a for a, b in zip(x, x[1:])]
    if all(v > 0 for v in x) and all(d > 0 for d in steps) and x[-1] / x[0] > 100.0:
        ratios = [b / a for a, b in zip(x, x[1:])]
        if max(steps) > 20.0 * min(steps) and max(ratios) < 3.0:
            return "FCS", "FCS-CSV", {}  # lag times: steps grow with the lag (multi-tau)
    if not all(v >= 0 for v in x):
        return None
    columns = min(len(r) for r in rows)
    settings: dict = {"skiprows": leading, "x_on": columns >= 2,
                      "is_vv_vh": columns == 1 and ("l1" in meta or "l2" in meta)}
    if meta.get("dt", 0) > 0:
        settings["dt"] = meta["dt"]
    return "TCSPC", "TXT/CSV", settings  # a time axis, or the counts of a one-column decay


def container_entries(path: str | Path) -> list[tuple[str, str]]:
    """The datasets a measurement container contributes: ``[(kind, address), ...]``.

    One ``("photons", "<path>/<stream>")`` per photon stream, then one ``("bursts",
    "<path>/<run>")`` per burst run, oldest first: the runs a burst search (or a fusion of one)
    wrote, then the burst tables an import wrote (:data:`BURST_RUN_OPERATIONS`).
    """
    from chisurf.core.fio.address import join_address
    from chisurf.core.fio.analysis_path import list_runs, split_artifact_name
    from chisurf.core.fio.fluorescence.burst_tree import TABLE
    from chisurf.core.fio.pto import Measurement

    path = Path(path)
    entries: list[tuple[str, str]] = []
    with Measurement.open(path, writable=False) as measurement:
        for name in measurement.photon_member_names():
            entries.append(("photons", join_address(path, name)))
        runs = list_runs(path, operation="burst_selection")
        # A burst table an import wrote (a BID selection) is a run too: the burst grain under the
        # burst table's name (``<run>/bursts``).
        for obj in measurement.artifacts():
            operation = measurement.tag(obj.uid, "_mmfdb_operation.operation_type")
            if operation not in BURST_RUN_OPERATIONS or operation == "burst_selection":
                continue
            if measurement.tag(obj.uid, "_mmfdb_artifact.row_grain") != "burst":
                continue
            run, table = split_artifact_name(str(obj.name))
            if table == TABLE and run not in runs:
                runs.append(run)
    for run in runs:
        entries.append(("bursts", join_address(path, run) if run else str(path)))
    return entries
