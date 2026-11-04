"""Safe per-measurement file names, the way the MT200 writes them.

The SymPhoTime workspace on the measurement PC keeps one directory per session under
``C:\\Measurements`` -- ``<INITIALS>_<YYYYMMDD>_<description>.sptw`` (``TP_20260930_JH_
FluoresceinFCS.sptw``, ``DM_20260808_MalE_211_322_Atto655.sptw``) -- and inside it, one
file *family* per measurement: ``<name>.ptu`` (the raw stream), ``<name>.pck`` and
``<name>_OFCS.pqres`` / ``_OTCSPC.pqres`` / ``_OFLIM.pqres`` (the analysis results). A
name taken twice is suffixed ``_1``, ``_2`` ... (``FCS_Fitting.pqres`` next to
``FCS_Fitting_1.pqres`` .. ``_11.pqres``) rather than overwritten. Real sessions bend the
scheme -- ``MR20260307`` without the underscore, ``20261028_Test_TP`` date-first, names
with spaces (``Green dye``), a stray ``µ`` (``0p125µM``) and ``$`` -- so this module
*generates* the canonical form and never renames existing data.

Everything here is Windows-safe first (the files land on ``C:\\Measurements`` and
``Z:\\microtime200``), case-insensitive (NTFS folds case, so ``Test`` and ``test``
collide even on a case-sensitive checkout), and collision-free by construction: a name is
only "used" once an exclusive first file exists, and :func:`next_available` always picks a
free candidate. Reservation uses the metadata sidecar (``<stem>.meta.json``) as the
family's tombstone: ``os.open(..., O_CREAT | O_EXCL)`` is atomic on NTFS, SMB and POSIX
alike, so two record starts can never silently share a measurement.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

_log = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_MAX_COMPONENT",
    "MEASUREMENT_META_SUFFIX",
    "MeasurementSlot",
    "initials",
    "measurement_stem",
    "next_available",
    "sanitize_component",
    "session_dir_name",
    "unique_session_dir",
]

#: Longest generated name component (NTFS allows 255; leave headroom for suffixes).
DEFAULT_MAX_COMPONENT = 80
#: The sidecar that reserves a measurement's name (written by :class:`MeasurementSlot`).
MEASUREMENT_META_SUFFIX = ".meta.json"

_FORBIDDEN = '<>:"/\\|?*'
_WHITESPACE = re.compile(r"\s+")
#: CON, PRN, AUX, NUL, COM1-9, LPT1-9 -- bare or with any extension, any case.
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$", re.IGNORECASE)
#: Micro signs the NFKD fold would not turn into an ASCII ``u`` on its own.
_MICRO = {"\u00b5": "u", "\u03bc": "u"}
_FALLBACK = "measurement"


def sanitize_component(text: str, *, max_length: int = DEFAULT_MAX_COMPONENT,
                       fold: bool = True) -> str:
    """Return ``text`` as one Windows-safe path component.

    Replaces the forbidden characters (``<>:"/\\|?*`` and control codes) and any
    whitespace run with ``_`` / single spaces, folds accents (``é`` -> ``e``) and micro
    signs (``µ`` -> ``u``) when *fold*, strips leading/trailing spaces and dots (a
    trailing dot or space is silently dropped by Windows), avoids the reserved device
    names by appending ``_``, and caps the length.  Never returns an empty string.
    Existing data is never passed through here -- this is for names this module generates.
    """
    text = str(text or "")
    for micro, ascii_u in _MICRO.items():
        text = text.replace(micro, ascii_u)
    if fold:
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
    out = []
    for ch in text:
        code = ord(ch)
        if ch in "\t\n\r":
            out.append(" ")
        elif code < 0x20 or code == 0x7F or ch in _FORBIDDEN:
            out.append("_")
        else:
            out.append(ch)
    cleaned = _WHITESPACE.sub(" ", "".join(out)).strip().strip(".")
    cleaned = re.sub(r"_ _", " ", cleaned)  # a replaced run reads better as a space
    cleaned = cleaned.strip().strip(".")
    if not cleaned:
        cleaned = _FALLBACK
    if _RESERVED.match(cleaned):
        cleaned = "_" + cleaned  # prefixed: NUL.txt_ would still look reserved to Windows
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(" .") or _FALLBACK
    return cleaned


def initials(operator: str) -> str:
    """The session-directory initials: ``"Thomas Peulen"`` -> ``"TP"``, ``"dm"`` -> ``"DM"``.

    An operator who is already initials stays as they are (uppercased); a name without
    letters falls back to ``"OP"``.
    """
    operator = str(operator or "").strip()
    words = [w for w in re.split(r"[^0-9A-Za-zÀ-ɏ]+", operator, flags=re.UNICODE) if w]
    if len(operator) <= 3 and operator.isalpha():
        return operator.upper()
    letters = "".join(w[0] for w in words if w[0].isalpha())
    return (letters or "OP").upper()


def session_dir_name(operator: str, when: datetime.datetime | None = None,
                     description: str = "") -> str:
    """``TP_20260930_JH_FluoresceinFCS`` -- the observed session-directory convention.

    The date is the measurement day (local time, YYYYMMDD); the description is sanitized
    and may be empty, in which case the name is just ``<INITIALS>_<YYYYMMDD>``.  The
    callers add the directory (see :func:`unique_session_dir`), which resolves the rare
    same-name-same-day collision with a ``_1`` suffix instead of failing.
    """
    when = when.astimezone() if when and when.tzinfo else (when or datetime.datetime.now().astimezone())
    parts = [initials(operator), when.strftime("%Y%m%d")]
    description = str(description or "").strip()
    if description:
        parts.append(sanitize_component(description, max_length=60))
    return "_".join(parts)


def next_available(stem: str, existing: Iterable[str], *, sep: str = "_",
                   start: int = 1, limit: int = 1000) -> str:
    """The first free name: ``stem``, then ``stem_1``, ``stem_2`` ... never an existing one.

    *existing* are names already on disk (any case); comparison is case-insensitive
    because NTFS (and macOS's default APFS) fold it.  When *stem* carries a file
    extension, the counter goes before it, as SymPhoTime does:
    ``FCS_Fitting.pqres`` -> ``FCS_Fitting_1.pqres``.  ``sep`` carries the observed
    styles: ``"_"`` (``CF532_1``), ``""`` (``CF5321``), ``"r"`` (``H2O_181r2``).
    """
    taken = {str(name).lower() for name in existing}
    stem = str(stem)
    if stem.lower() not in taken:
        return stem
    match = re.match(r"^(.*)(\.[A-Za-z0-9]{1,8})$", stem)
    root, extension = match.groups() if match else (stem, "")
    for index in range(start, start + limit):
        candidate = f"{root}{sep}{index}{extension}"
        if candidate.lower() not in taken:
            return candidate
    raise RuntimeError(f"no free name derived from {stem!r} within {limit} attempts")


def measurement_stem(base: str, when: datetime.datetime | None = None, *,
                     style: str = "plain") -> str:
    """A measurement's stem: *plain* ``CF532``, *datetime* ``CF532_154701``, *date* ``CF532_20261030``.

    The MT200 measurements name themselves after the sample and conditions
    (``buffer_APO_0d_60b1``) and let the replicate counter (or nothing) distinguish
    repeats -- so *plain* is the default and uniqueness comes from
    :func:`next_available` / :class:`MeasurementSlot`, not from a forced timestamp.
    """
    stem = sanitize_component(base)
    if style == "plain":
        return stem
    moment = when.astimezone() if when and when.tzinfo else (when or datetime.datetime.now().astimezone())
    if style == "datetime":
        return f"{stem}_{moment.strftime('%H%M%S')}"
    if style == "date":
        return f"{stem}_{moment.strftime('%Y%m%d')}"
    raise ValueError(f"unknown stem style {style!r} (plain, datetime, date)")


def _existing_stems_lower(directory: Path) -> set[str]:
    """Every file and directory name in *directory*, lowercased (NTFS folds case)."""
    try:
        return {entry.name.lower() for entry in os.scandir(directory)}
    except FileNotFoundError:
        return set()


def _taken_measurement_stems(directory: Path) -> set[str]:
    """The measurement stems already claimed in *directory*, from either family file.

    A stem is taken when its ``.ptu`` *or* its ``<stem>.meta.json`` sidecar exists --
    the sidecar alone is a live reservation.
    """
    taken: set[str] = set()
    for name in _existing_stems_lower(directory):
        if name.endswith(".ptu"):
            taken.add(name[: -len(".ptu")])
        elif name.endswith(MEASUREMENT_META_SUFFIX):
            taken.add(name[: -len(MEASUREMENT_META_SUFFIX)])
        else:
            taken.add(name)
    return taken


class MeasurementSlot:
    """One measurement's reserved name and its file family inside a session directory.

    Reserving is the exclusive creation of ``<stem>.meta.json`` -- atomic on Windows,
    SMB shares and POSIX -- so a second :meth:`create` with the same base name is forced
    onto the next free stem instead of overwriting.  The rest of the family grows around
    it: ``slot.ptu_path`` is where the stream is written, :meth:`write_meta` replaces the
    placeholder sidecar with real metadata.  Nothing is ever deleted implicitly;
    :meth:`abandon` (for a measurement that never started) removes *only* the sidecar
    while it is still the untouched placeholder and no data file appeared.
    """

    def __init__(self, directory: Path, stem: str) -> None:
        self.directory = Path(directory)
        self.stem = str(stem)
        self.meta_path = self.directory / f"{self.stem}{MEASUREMENT_META_SUFFIX}"
        self.ptu_path = self.directory / f"{self.stem}.ptu"
        self._placeholder = True
        self.reserved_at = datetime.datetime.now().astimezone()

    @classmethod
    def create(cls, directory: Path | str, base: str, *, when: datetime.datetime | None = None,
               style: str = "plain", sep: str = "_", meta: dict[str, Any] | None = None,
               attempts: int = 1000) -> MeasurementSlot:
        """Reserve the next free measurement name in *directory* and return its slot.

        ``base`` is the sample/conditions text (``"buffer_APO_0d_60b"``); *style* and
        *sep* shape the stem exactly as in :func:`measurement_stem` and
        :func:`next_available`.  Raises ``FileExistsError`` only if *attempts* candidates
        are all taken -- never overwrites an existing file.
        """
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        stem = measurement_stem(base, when, style=style)
        # Two same-second starts (or two processes) must not share a name: resolve against
        # the taken stems, then let the exclusive create arbitrate a lost race.
        for _attempt in range(3):
            candidate = next_available(stem, _taken_measurement_stems(directory), sep=sep,
                                       limit=attempts)
            slot = cls(directory, candidate)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            try:
                handle = os.open(slot.meta_path, flags)
            except FileExistsError:
                _log.warning("name reservation lost a race for %s; retrying", slot.meta_path)
                continue
            with os.fdopen(handle, "w", encoding="utf-8") as fh:
                json.dump(meta if meta is not None else {"reserved_at": slot.reserved_at.isoformat()},
                          fh, indent=2, sort_keys=True)
            _log.info("reserved measurement %s in %s", slot.stem, directory)
            return slot
        raise RuntimeError(f"could not reserve a measurement name from {stem!r} in {directory}")

    @property
    def placeholder(self) -> bool:
        """True while the sidecar still is the untouched reservation placeholder."""
        return self._placeholder

    def family_paths(self) -> dict[str, Path]:
        """The files one measurement may consist of, whether or not they exist yet."""
        return {"ptu": self.ptu_path, "meta": self.meta_path}

    def write_meta(self, meta: dict[str, Any]) -> None:
        """Replace the placeholder sidecar with the real metadata document."""
        tmp = self.meta_path.with_suffix(MEASUREMENT_META_SUFFIX + ".tmp")
        tmp.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.meta_path)
        self._placeholder = False

    def abandon(self) -> bool:
        """Remove the reservation when the measurement never produced data.

        Deletes the sidecar only while it is still the untouched placeholder and no other
        family file (``.ptu``) appeared; returns whether anything was removed.  A
        measurement with data is never touched -- call a transfer instead.
        """
        if not self._placeholder or self.ptu_path.exists():
            return False
        try:
            self.meta_path.unlink()
        except FileNotFoundError:
            return False
        _log.info("abandoned empty measurement %s", self.stem)
        return True

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"MeasurementSlot({self.directory / self.stem!s})"


def unique_session_dir(root: Path | str, name: str) -> Path:
    """Create ``root/name``, or ``root/name_1`` ... when taken; return the directory.

    Creating the directory *is* the reservation (``mkdir`` is atomic), so two sessions
    started within the same minute never share one.  The *root* itself must exist -- on a
    disconnected network drive this fails loudly instead of silently creating a local
    look-alike folder.
    """
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"session root does not exist: {root}")
    candidate = sanitize_component(name, max_length=120)
    taken = _existing_stems_lower(root)
    candidate = next_available(candidate, taken)
    directory = root / candidate
    directory.mkdir()
    return directory
