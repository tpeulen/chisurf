"""One measurement, one file — the PTO.MFDB seam.

Analysis output used to be a directory tree whose parts were related only by
filename convention, so the relationship died the moment somebody renamed a
folder. This module writes it instead as one photon container: the instrument
file kept verbatim at the front, every result an artifact beside it, and every
name taken from the mmCIF dictionaries rather than invented here.

The normative rules are in [the PTO.MFDB profile](/specs/pto-mfdb.md); this is
the only code that implements them, so a plugin never touches ``tttrlib.PtoFile``
directly and no writer has to remember the conventions.

Three things are worth knowing before using it.

**The instrument file is the truth.** It goes in byte-for-byte and is never
decoded into a second copy beside itself — ``tttrlib.TTTR`` reads it in place
out of the container, so a ``.pto`` is the size of the raw data plus the
results, not twice the raw data. :meth:`Measurement.disassemble` puts it back on
disk identical to what went in, and verifies the checksum while doing it.

**Nothing is joined by position.** Every table declares what one of its rows
*is* (:mod:`row_grain`), and a relation between two tables is a declared key,
not an alignment of row counts. This is the whole reason a dwell table and a
fused-burst table can live here at all: they are finer and coarser than the
bursts they relate to, and a format that can only carry one row per burst has
nowhere to put either.

**Re-running an analysis replaces it.** The identity of a run is the hash of its
settings, so recomputing with the same settings rewrites that artifact in place
and changing a setting produces a new one. Nothing accumulates, and parameters
never have to be encoded in a file name.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
import warnings
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

logger = logging.getLogger(__name__)

__all__ = [
    "CONTAINER_FORMAT",
    "Measurement",
    "PROFILE",
    "PROFILE_READ_VERSION",
    "PROFILE_VERSION",
    "PtoMfdbError",
    "SUFFIX",
    "is_measurement",
]

#: Name of the profile written into every file.
PROFILE = "PTO.MFDB"

#: Version of the profile this module writes.
PROFILE_VERSION = "1.1"

#: Minimum profile version required to read what this module writes. A reader
#: implementing less than this must refuse the file rather than misread it.
PROFILE_READ_VERSION = 1

#: The container underneath the profile.
CONTAINER_FORMAT = "pto"
CONTAINER_FORMAT_VERSION = "1.0"

SUFFIX = ".pto"

#: Block size for streaming digests. Large enough that the syscall overhead
#: disappears, small enough that an 8 GiB payload never lands in memory.
_BLOCK = 1 << 20

# -- mmCIF item names ---------------------------------------------------------
# Tag names ARE dictionary item names. Spelling them once here is what keeps
# thirty writers from inventing thirty dialects.

_ARTIFACT_ID = "_mmfdb_artifact.artifact_id"
_ARTIFACT_KIND = "_mmfdb_artifact.artifact_kind"
_DATA_FORMAT = "_mmfdb_artifact.data_format"
_ROW_GRAIN = "_mmfdb_artifact.row_grain"
_ROW_COUNT = "_mmfdb_artifact.row_count"
_CHECKSUM = "_mmfdb_artifact.checksum"
_CHECKSUM_ALGORITHM = "_mmfdb_artifact.checksum_algorithm"
_SIZE_BYTES = "_mmfdb_artifact.size_bytes"
_MIME_TYPE = "_mmfdb_artifact.mime_type"
_FILE_PATH = "_mmfdb_artifact.file_path"

_OPERATION_TYPE = "_mmfdb_operation.operation_type"
_SETTINGS_JSON = "_mmfdb_operation.settings_json"
_SETTINGS_HASH = "_mmfdb_operation.settings_hash"
_SOFTWARE_PACKAGE = "_mmfdb_operation.software_package"
_SOFTWARE_VERSION = "_mmfdb_operation.software_version"
_DICTIONARY_VERSION = "_mmfdb_operation.dictionary_version"
_DICTIONARY_HASH = "_mmfdb_operation.dictionary_hash"

_RELATIONSHIP_TYPE = "_mmfdb_edge.relationship_type"
_SOURCE_ROW_COLUMN = "_mmfdb_edge.source_row_column"
_TARGET_ROW_COLUMN = "_mmfdb_edge.target_row_column"

_COLUMN_NAME = "_mmfdb_column.name"
_COLUMN_UNITS = "_mmfdb_column.units"
_COLUMN_ITEM = "_mmfdb_column.item"
_COLUMN_DESCRIPTION = "_mmfdb_column.description"

_CONTAINER_PROFILE = "_mmfdb_container.profile"
_CONTAINER_PROFILE_VERSION = "_mmfdb_container.profile_version"
_CONTAINER_PROFILE_READ_VERSION = "_mmfdb_container.profile_read_version"
_CONTAINER_FORMAT = "_mmfdb_container.format"
_CONTAINER_FORMAT_VERSION = "_mmfdb_container.format_version"
_CONTAINER_DICTIONARY_VERSION = "_mmfdb_container.dictionary_version"
_CONTAINER_DICTIONARY_HASH = "_mmfdb_container.dictionary_hash"

#: ``data_format`` for a payload written as a tttrlib columnar store.
_DSTORE = "dstore"


#: The plain-text preamble every container carries as its first object.
#:
#: A container is only useful for as long as something can read it. The library
#: that wrote this may not be installed, may not build, or may not exist; the
#: format is EBML and therefore walkable by hand, but only if the reader knows
#: that. So the file says so itself, in ASCII, before anything else in it.
#:
#: Deliberately terse and deliberately not Markdown: it is meant to be read
#: with `strings file.pto | head -40`, or in a hex editor, by someone who has
#: this file and nothing else. It is the first *object*, not the first bytes —
#: the container's two index reserves come before it, so it begins around 16 kB
#: in rather than at zero.
README = """\
PTO.MFDB CONTAINER -- one measurement, one file.
Profile {profile} v{profile_version}; container {container} v{container_version}.

WHAT THIS IS
  An EBML document (RFC 8794), DocType "pto". Same framing as Matroska, and it
  reuses Matroska element IDs where the meaning matches. Every element is
  ID + SIZE + DATA; both ID and SIZE are variable-length integers whose leading
  1-bit gives the byte count. Unknown IDs are skipped by SIZE, so a partial
  reader still walks the whole file.

HOW TO READ IT WITHOUT THIS LIBRARY
  1. EBML header (0x1A45DFA3), then one Segment (0x18538067).
  2. Inside Segment: two SeekHead (0x114D9B74) indexes. The live one is the one
     with the greater PtoGeneration (0x1E54F010) whose CRC-32 verifies. If
     neither does, walk Segment's children in order -- every element carries its
     own size, so the index is an optimisation, not the truth.
  3. Each object is an Attachments (0x1941A469) holding one AttachedFile
     (0x61A7): FileUID 0x46AE, PtoKind 0x1E54F001, PtoEncoding 0x1E54F002,
     FileName 0x466E, FileData 0x465C. The payload is FileData's bytes, verbatim.
  4. Tags (0x1254C367) carry metadata. A Tag targets an object by
     TagAttachmentUID (0x63C6); TagName (0x45A3) is an mmCIF item name and the
     value is one of TagString (0x4487) or PtoTag* (0x1E54F02x).

WHAT THE OBJECTS ARE
  PtoKind says what an object is for; PtoEncoding says how to decode it. Both
  are terms from the MMFDB mmCIF dictionary, not free text.
    readme            this text
    tttr_photon_stream  the instrument file, byte-for-byte as recorded
    sample_metadata   the measurement's mmCIF/flrCIF metadata block
    burst_table, dwell_table, pixel_map, ...  results, encoding "dstore"
  Encoding "dstore" is a columnar table: magic "TTTRSTOR", a 48-byte header
  (version, flags, directory offset+size, file size, FNV-1a of the directory),
  then blobs, then the directory. Columns are contiguous little-endian arrays.
  Encoding "ptu"/"spc"/"ht3"/... is the vendor file unchanged -- write FileData
  to a file and any reader of that format opens it.

RECOVERING THE ORIGINAL DATA
  Find the AttachedFile whose PtoKind is tttr_photon_stream and write its
  FileData to a file. That is the instrument file as recorded, bit for bit; its
  _mmfdb_artifact.checksum tag is the SHA-256 to verify against. Nothing in this
  container is a lossy re-encoding of it.

WHAT IS NOT HERE
  No compression. No encryption. No external references: every byte a reader
  needs is in this file.

Full specification: doc/formats/pto.rst (container) and the PTO.MFDB profile
(this layer) in the ChiSurf knowledge bundle, okf/specs/pto-mfdb.md.
"""

#: Instrument container suffix -> ``_mmfdb_artifact.data_format`` term. A
#: suffix this does not know is carried as ``unknown`` rather than guessed at:
#: the bytes round-trip either way, and a wrong term is worse than no term.
_FORMAT_BY_SUFFIX = {
    ".ptu": "ptu",
    ".ht3": "ptu",
    ".pt3": "ptu",
    ".spc": "spc",
    ".set": "spc",
    ".sm": "tttr",
    ".ttr": "tttr",
    ".h5": "photon_hdf5",
    ".hdf5": "photon_hdf5",
    ".bin": "bin",
    ".tif": "tiff",
    ".tiff": "tiff",
}

#: Suffixes a reader must be handed together with their primary, because the
#: primary is not decodable alone. A Becker & Hickl ``.spc`` keeps half its
#: header in a ``.set`` beside it.
_SIDECAR_SUFFIXES = {".spc": (".set",)}


class PtoMfdbError(RuntimeError):
    """A container could not be written or read as the profile requires."""


def _tttrlib() -> Any:
    """Import ``tttrlib`` on first use.

    Kept out of module scope so importing this module does not pull in the
    compiled extension before anything asks for a container.

    Returns
    -------
    module
    """
    import tttrlib

    return tttrlib


def _vocabulary() -> Any:
    """Return the dictionary that defines every term this module writes.

    Both the bundled dictionaries and the export-only one are loaded: the
    container/profile terms describe a *serialisation* and are deliberately
    kept out of the bundled set so that schema reconciliation does not
    materialise a table for them.

    Returns
    -------
    mmfdb.schema.pdbx_metadata.MmcifDictionary
    """
    from mmfdb.schema.pdbx_metadata import MmcifDictionary

    paths = [
        MmcifDictionary._resolve_dic(name)
        for name in (*MmcifDictionary.BUNDLED_DICTS, *MmcifDictionary.EXPORT_ONLY_DICTS)
    ]
    return MmcifDictionary(*paths)


_VOCABULARY: Any = None


def _terms(item: str) -> set[str]:
    """Return the enumerated values one dictionary item allows.

    Parameters
    ----------
    item : str
        Full mmCIF item name, e.g. ``"_mmfdb_artifact.artifact_kind"``.

    Returns
    -------
    set of str
    """
    global _VOCABULARY
    if _VOCABULARY is None:
        _VOCABULARY = _vocabulary()
    return set(_VOCABULARY.get_enumerations(item))


def _check_term(value: str, item: str) -> str:
    """Return *value* if the dictionary allows it for *item*, else raise.

    The profile defines no vocabulary of its own, so a term that is not in the
    dictionary is a writer inventing a word. Catching it here means the file is
    never written rather than being written unqueryable.

    Parameters
    ----------
    value : str
        The candidate term.
    item : str
        Full mmCIF item name whose enumeration constrains it.

    Returns
    -------
    str
        ``value``.

    Raises
    ------
    PtoMfdbError
        If the dictionary does not list ``value``.
    """
    allowed = _terms(item)
    if not allowed:
        raise PtoMfdbError(
            f"{item} has no enumeration in the loaded dictionaries; "
            "the vocabulary failed to load, so nothing can be validated"
        )
    if value not in allowed:
        raise PtoMfdbError(
            f"{value!r} is not a value of {item}. Add the term to the MMFDB "
            f"extension dictionary before writing it; the profile invents none."
        )
    return value


def _sha256_of_path(path: Path) -> tuple[str, int]:
    """Digest a file without holding it in memory.

    Parameters
    ----------
    path : Path
        File to read.

    Returns
    -------
    tuple of (str, int)
        Lowercase hexadecimal digest and the size in octets.
    """
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(_BLOCK), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _settings_hash(settings: Mapping[str, Any] | None) -> str:
    """Return the identity of a run, from its settings.

    Canonicalised so that key order and float formatting cannot make one run
    look like two.

    Parameters
    ----------
    settings : mapping or None
        The analysis parameters.

    Returns
    -------
    str
        Lowercase hexadecimal SHA-256 of the canonical JSON.
    """
    blob = json.dumps(settings or {}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def is_measurement(path: str | Path) -> bool:
    """Return whether *path* is a photon container.

    Answers from the file's own header rather than its suffix, and answers
    ``False`` quietly for anything else, including a file that does not exist.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    bool
    """
    try:
        return bool(_tttrlib().is_pto_file(str(path)))
    except Exception:
        return False


class Measurement:
    """One measurement: the instrument data, and everything computed from it.

    Use as a context manager — the container commits on a clean exit and is
    left untouched on an exception, because nothing in PTO is visible before a
    commit.

    Examples
    --------
    >>> with Measurement.create("m000.ptu") as m:            # doctest: +SKIP
    ...     photons = m.instrument_uid
    ...     m.put_table(
    ...         "bursts", bursts_frame,
    ...         artifact_kind="burst_table",
    ...         operation_type="burst_selection",
    ...         row_grain="burst",
    ...         parameters={"min_photons": 60},
    ...         derived_from=photons,
    ...     )
    """

    def __init__(self, handle: Any, path: Path, *, writable: bool = True) -> None:
        self._f = handle
        self._path = Path(path)
        self._writable = bool(writable)
        self._instrument_uid = 0

    # -- construction ---------------------------------------------------------

    @classmethod
    def create(
        cls,
        raw_path: str | Path,
        *,
        out_dir: str | Path | None = None,
        title: str = "",
        artifact_kind: str = "tttr_photon_stream",
    ) -> "Measurement":
        """Start a container from an instrument file.

        The instrument file is copied in **verbatim** as the first object and is
        never rewritten afterwards, so its offset is stable for the life of the
        container and no recomputation can disturb it. The original on disk is
        left alone.

        Parameters
        ----------
        raw_path : str or Path
            The instrument file (``.ptu``, ``.spc``, ``.ht3``, ...).
        out_dir : str or Path, optional
            Directory for the container. Defaults to beside *raw_path*, which
            is wrong for read-only source media and right everywhere else.
        title : str, optional
            Human title. Defaults to the instrument file's stem.
        artifact_kind : str, optional
            What the source *is*, as an ``_mmfdb_artifact.artifact_kind`` term.
            Defaults to a photon stream, which is what nearly every measurement
            here starts as — but not all of them: an ebFRET run starts from
            binned traces, and calling those a photon stream would be a
            statement about the file that is simply false, in the one field a
            reader consults to decide how to open it.

        Returns
        -------
        Measurement

        Raises
        ------
        PtoMfdbError
            If the container cannot be created.
        """
        raw = Path(raw_path)
        if not raw.exists():
            raise PtoMfdbError(f"no such instrument file: {raw}")

        target_dir = Path(out_dir) if out_dir is not None else raw.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / (raw.stem + SUFFIX)

        tttrlib = _tttrlib()
        handle = tttrlib.PtoFile()
        if not handle.create(str(target), title or raw.stem):
            raise PtoMfdbError(f"could not create {target}: {handle.error()}")
        handle.set_writing_app(_writing_app())

        self = cls(handle, target)
        self._stamp_versions()
        self._add_readme()
        self._instrument_uid = self._add_instrument(raw, artifact_kind)
        return self

    @classmethod
    def open(cls, path: str | Path, *, writable: bool = False) -> "Measurement":
        """Open an existing container.

        Parameters
        ----------
        path : str or Path
        writable : bool, optional
            Open for writing. A read-only handle refuses every mutation rather
            than failing partway through one.

        Returns
        -------
        Measurement

        Raises
        ------
        PtoMfdbError
            If the file is not a container, or cannot be opened.
        """
        handle = _tttrlib().PtoFile()
        if not handle.open(str(path), writable):
            raise PtoMfdbError(f"could not open {path}: {handle.error()}")
        self = cls(handle, Path(path), writable=writable)
        for obj in handle.objects():
            if obj.kind == "tttr_photon_stream":
                self._instrument_uid = obj.uid
                break
        return self

    def __enter__(self) -> "Measurement":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        # A read-only handle has nothing to commit, and asking it to would
        # turn an ordinary read into an error on the way out of the block.
        if exc_type is None and self._writable:
            self.commit()
        self.close()
        return False

    # -- identity -------------------------------------------------------------

    @property
    def path(self) -> Path:
        """Path of the container on disk."""
        return self._path

    @property
    def instrument_uid(self) -> int:
        """UID of the instrument object, or ``0`` if the file has none."""
        return self._instrument_uid

    def source(self, member: str = "") -> str:
        """Return a spec that opens the photon data, for ``open_tttr``.

        Parameters
        ----------
        member : str, optional
            Name of a specific embedded instrument file. Omit when there is
            only one, which is the usual case.

        Returns
        -------
        str
            Either ``"<path>"`` or ``"<path>|<member>"``.
        """
        return f"{self._path}|{member}" if member else str(self._path)

    # -- writing --------------------------------------------------------------

    def put_table(
        self,
        name: str,
        table: Any,
        *,
        artifact_kind: str,
        operation_type: str,
        row_grain: str,
        parameters: Mapping[str, Any] | None = None,
        derived_from: int | Sequence[int] | None = None,
        source_row_column: str = "",
        target_row_column: str = "",
        units: Mapping[str, str] | None = None,
        items: Mapping[str, str] | None = None,
        reserve: int | None = None,
    ) -> int:
        """Write a table, replacing any earlier run with the same settings.

        Parameters
        ----------
        name : str
            Label for the object. Labels need not be unique; identity is the
            artifact id.
        table : pandas.DataFrame or tttrlib.DataStore
            The data. A frame is converted through the columnar seam, so dtypes
            and per-column validity masks survive.
        artifact_kind : str
            A ``_mmfdb_artifact.artifact_kind`` term.
        operation_type : str
            A ``_mmfdb_operation.operation_type`` term.
        row_grain : str
            A ``_mmfdb_artifact.row_grain`` term — what one row *is*.
        parameters : mapping, optional
            The analysis settings. Their hash is the identity of the run.
        derived_from : int or sequence of int, optional
            Parent object UIDs. Several are allowed: a fused burst genuinely
            has more than one parent.
        source_row_column, target_row_column : str, optional
            Columns the parent and this table join on. Supply them whenever the
            grains differ, so the relation is declared rather than inferred
            from row counts.
        units : mapping, optional
            ``{column: unit}`` using ``_mmfdb_column.units`` terms — what makes
            a number in the table mean something without the reader having to
            know the naming convention it was written under.
        items : mapping, optional
            ``{column: mmCIF item name}``, so a table can be projected onto the
            dictionary rather than matched by name.
        reserve : int, optional
            Bytes of slack left after the payload so a later, slightly larger
            run can be written in place. Defaults to a quarter of the payload.

        Returns
        -------
        int
            The object UID.
        """
        self._require_writable()
        _check_term(artifact_kind, _ARTIFACT_KIND)
        _check_term(operation_type, _OPERATION_TYPE)
        _check_term(row_grain, _ROW_GRAIN)

        store = self._as_store(table)
        self._describe_columns(store, units, items)
        run = _settings_hash(parameters)

        existing = self._find_run(operation_type, run, artifact_kind, name)
        tttrlib = _tttrlib()
        if existing:
            if not tttrlib.pto_update_store(self._f, existing, store):
                raise PtoMfdbError(f"could not update {name}: {self._f.error()}")
            uid = existing
        else:
            rows = int(store.n_rows())
            slack = reserve if reserve is not None else max(8192, rows * 64)
            uid = tttrlib.pto_add_store(self._f, artifact_kind, name, store, slack)
            if not uid:
                raise PtoMfdbError(f"could not write {name}: {self._f.error()}")

        self._describe(
            uid,
            data_format=_DSTORE,
            row_grain=row_grain,
            operation_type=operation_type,
            parameters=parameters,
            run=run,
            derived_from=derived_from,
            source_row_column=source_row_column,
            target_row_column=target_row_column,
        )
        return uid

    def put_metadata(
        self,
        metadata: Mapping[str, Mapping[str, Any]] | str,
        *,
        name: str = "metadata",
    ) -> int:
        """Record what the measurement *is*, beside what was done to it.

        Provenance says a burst table came from a photon stream by a burst
        search. It does not say which sample, which dyes, which buffer, which
        instrument — and a file that cannot answer those is not a record of a
        measurement, it is a record of a computation.

        The metadata is written as an mmCIF block, so it is the same vocabulary
        the rest of the container uses and the same one a deposition wants. It
        is carried whole rather than flattened into tags: a category with
        several rows — two probes, three detector channels — is a loop, and tags
        are name/value pairs.

        Nothing is invented or inferred. A caller that has no sample metadata
        passes none, and the container simply has no such object; an empty block
        would claim the measurement was described when it was not.

        Parameters
        ----------
        metadata : mapping or str
            Either ``{category: {item: value}}`` — for example
            ``{"flr_sample": {"sample_description": "Cy3B-Cy5 dsDNA"}}`` — or a
            ready-made mmCIF text block, which is written as it is.
        name : str, optional
            Label for the object.

        Returns
        -------
        int
            The object UID.

        Raises
        ------
        PtoMfdbError
            If a category or item is not in the loaded dictionaries. The point
            of using mmCIF here is that the words mean something; an undeclared
            one would be prose in a field that looks structured.
        """
        self._require_writable()
        text = metadata if isinstance(metadata, str) else _metadata_to_cif(metadata)
        payload = text.encode("utf-8")
        uid = self._f.add("sample_metadata", "cif", name, payload)
        if not uid:
            raise PtoMfdbError(f"could not write {name}: {self._f.error()}")
        self._describe(
            uid,
            data_format="cif",
            checksum=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
            mime_type="chemical/x-cif",
        )
        return uid

    def metadata(self) -> str:
        """Return the measurement's mmCIF metadata block, or ``""``.

        Returns
        -------
        str
            The block as written. Empty when the container carries none, which
            means the measurement was never described — not that it has no
            sample.
        """
        for obj in self._f.objects():
            if obj.kind == "sample_metadata":
                return bytes(self._f.read(obj.uid)).decode("utf-8", "replace")
        return ""

    def put_blob(
        self,
        name: str,
        data: bytes,
        *,
        artifact_kind: str,
        data_format: str,
        operation_type: str = "",
        parameters: Mapping[str, Any] | None = None,
        derived_from: int | Sequence[int] | None = None,
        mime_type: str = "",
    ) -> int:
        """Write an opaque payload — an image, a document, a vendor file.

        Parameters
        ----------
        name : str
        data : bytes
        artifact_kind : str
            A ``_mmfdb_artifact.artifact_kind`` term.
        data_format : str
            A ``_mmfdb_artifact.data_format`` term.
        operation_type : str, optional
            A ``_mmfdb_operation.operation_type`` term, when the payload is a
            result rather than something carried along.
        parameters : mapping, optional
        derived_from : int or sequence of int, optional
        mime_type : str, optional

        Returns
        -------
        int
            The object UID.
        """
        self._require_writable()
        _check_term(artifact_kind, _ARTIFACT_KIND)
        _check_term(data_format, _DATA_FORMAT)
        if operation_type:
            _check_term(operation_type, _OPERATION_TYPE)

        payload = bytes(data)
        uid = self._f.add(artifact_kind, data_format, name, payload)
        if not uid:
            raise PtoMfdbError(f"could not write {name}: {self._f.error()}")

        self._describe(
            uid,
            data_format=data_format,
            checksum=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
            operation_type=operation_type,
            parameters=parameters,
            run=_settings_hash(parameters) if operation_type else "",
            derived_from=derived_from,
            mime_type=mime_type,
        )
        return uid

    # -- reading --------------------------------------------------------------

    def artifacts(
        self,
        *,
        artifact_kind: str = "",
        operation_type: str = "",
    ) -> list[Any]:
        """List the objects in the container, optionally filtered.

        Parameters
        ----------
        artifact_kind : str, optional
        operation_type : str, optional

        Returns
        -------
        list of tttrlib.PtoObject
            In the order they were written.
        """
        out = []
        for obj in self._f.objects():
            if artifact_kind and obj.kind != artifact_kind:
                continue
            if operation_type and self.tag(obj.uid, _OPERATION_TYPE) != operation_type:
                continue
            out.append(obj)
        return out

    def get_store(self, ref: int | str) -> Any:
        """Read a table back as a store, with its column descriptions intact.

        Prefer this to :meth:`get_table`. A column's unit and mmCIF item are
        attributes *of the column*, and pandas has nowhere to put them — so a
        frame is the one shape of this table that cannot say a duration is
        milliseconds, which is the thing writing the units was for.

        Parameters
        ----------
        ref : int or str
            An object UID, or a name to look up.

        Returns
        -------
        tttrlib.DataStore

        Raises
        ------
        PtoMfdbError
            If there is no such object.
        """
        from chisurf.core.datastore import new_store

        uid = self._resolve(ref)
        store = new_store()
        _tttrlib().pto_read_store(self._f, uid, store)
        return store

    def get_table(self, ref: int | str) -> Any:
        """Read a table back as a :class:`pandas.DataFrame`.

        The convenience shape, for callers that already speak pandas. It
        **drops the column descriptions** — see :meth:`get_store`, which does
        not.

        Parameters
        ----------
        ref : int or str
            An object UID, or a name to look up.

        Returns
        -------
        pandas.DataFrame

        Raises
        ------
        PtoMfdbError
            If there is no such object.
        """
        from chisurf.core.datastore import dataframe_from_store

        return dataframe_from_store(self.get_store(ref))

    def tag(self, uid: int, item: str, default: Any = "") -> Any:
        """Return one tag value from an object, by mmCIF item name.

        Parameters
        ----------
        uid : int
            Object UID; ``0`` for the tags describing the file.
        item : str
            Full mmCIF item name.
        default : object, optional

        Returns
        -------
        object
            The tag's text, integer or float, or *default*.
        """
        tttrlib = _tttrlib()
        for t in self._f.tags_for(uid):
            if t.name != item:
                continue
            if t.type == tttrlib.PtoType_Text:
                return t.text
            if t.type in (tttrlib.PtoType_UInt, tttrlib.PtoType_UID):
                return t.u
            if t.type == tttrlib.PtoType_Int:
                return t.i
            if t.type == tttrlib.PtoType_Float:
                return t.d
            return default
        return default

    def parents(self, uid: int) -> list[int]:
        """Return the UIDs this object was derived from.

        Several is normal — fusing bursts produces a row with more than one
        parent, and the edge arity has to be able to say so.

        Parameters
        ----------
        uid : int

        Returns
        -------
        list of int
        """
        tttrlib = _tttrlib()
        return [
            t.u
            for t in self._f.tags_for(uid)
            if t.name == _RELATIONSHIP_TYPE and t.type == tttrlib.PtoType_UID
        ]

    # -- getting back out -----------------------------------------------------

    def verify(self) -> list[str]:
        """Check every recorded checksum against the stored bytes.

        Returns
        -------
        list of str
            Human-readable descriptions of every mismatch. Empty when the file
            is intact.
        """
        problems: list[str] = []
        for obj in self._f.objects():
            recorded = self.tag(obj.uid, _CHECKSUM)
            if not recorded:
                continue
            actual = hashlib.sha256(bytes(self._f.read(obj.uid))).hexdigest()
            if actual != recorded:
                problems.append(
                    f"{obj.name or obj.uid}: recorded {recorded[:16]}…, found {actual[:16]}…"
                )
        return problems

    def get_blob(self, ref: int | str) -> bytes:
        """Read an opaque payload back into memory, verifying it.

        The read half of :meth:`put_blob`. :meth:`extract` could already put one
        on disk, which is the right thing for a multi-gigabyte photon stream and
        the wrong thing for the small documents a container carries — a `.bid`
        selection, a settings file, a rendered image — where a temporary file is
        only a temporary file to clean up.

        The checksum is checked here as it is in :meth:`extract`, because
        "recoverable" without verification is only "probably recoverable".

        Parameters
        ----------
        ref : int or str
            Object UID or name.

        Returns
        -------
        bytes

        Raises
        ------
        PtoMfdbError
            If there is no such object, the read fails, or the payload does not
            match its recorded checksum.
        """
        import hashlib

        uid = self._resolve(ref)
        data = self._f.read(uid)
        if data is None:
            raise PtoMfdbError(f"could not read {ref}: {self._f.error()}")
        data = bytes(data)

        recorded = self.tag(uid, _CHECKSUM)
        if recorded:
            actual = hashlib.sha256(data).hexdigest()
            if actual != recorded:
                raise PtoMfdbError(
                    f"{ref} does not match its recorded checksum "
                    f"({recorded[:16]}… expected, {actual[:16]}… found)"
                )
        return data

    def extract(self, ref: int | str, destination: str | Path) -> Path:
        """Write one object back out as a file of its own, verifying it.

        Parameters
        ----------
        ref : int or str
            Object UID or name.
        destination : str or Path

        Returns
        -------
        Path
            The file written.

        Raises
        ------
        PtoMfdbError
            If extraction fails, or the payload does not match its checksum —
            "restorable" without verification is only "probably restorable".
        """
        uid = self._resolve(ref)
        out = Path(destination)
        out.parent.mkdir(parents=True, exist_ok=True)
        if not self._f.extract(uid, str(out)):
            raise PtoMfdbError(f"could not extract {ref}: {self._f.error()}")

        recorded = self.tag(uid, _CHECKSUM)
        if recorded:
            actual, _ = _sha256_of_path(out)
            if actual != recorded:
                raise PtoMfdbError(
                    f"{out} does not match its recorded checksum "
                    f"({recorded[:16]}… expected, {actual[:16]}… found)"
                )
        return out

    def disassemble(self, directory: str | Path) -> list[Path]:
        """Take the container apart into ordinary files.

        Sidecars land beside what they belong to, which is what a Becker &
        Hickl ``.spc`` needs: its reader looks for the ``.set`` next to it and
        would otherwise silently read half a header.

        Parameters
        ----------
        directory : str or Path

        Returns
        -------
        list of Path
            The files written.
        """
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        written = [Path(p) for p in self._f.disassemble(str(out))]
        if not written:
            raise PtoMfdbError(f"could not disassemble into {out}: {self._f.error()}")
        return written

    # -- lifecycle ------------------------------------------------------------

    def commit(self) -> None:
        """Make everything written since the last commit visible, atomically."""
        if not self._f.commit():
            raise PtoMfdbError(f"could not commit {self._path}: {self._f.error()}")

    def close(self) -> None:
        """Release the file handle."""
        self._f.close()

    # -- internals ------------------------------------------------------------

    def _require_writable(self) -> None:
        if not self._f.is_open():
            raise PtoMfdbError("the container is closed")
        if not self._writable:
            raise PtoMfdbError(
                f"{self._path} was opened read-only; reopen with writable=True"
            )

    def _resolve(self, ref: int | str) -> int:
        if isinstance(ref, int):
            uid = ref
        else:
            uid = self._f.find(ref)
        if not uid or not self._f.has(uid):
            raise PtoMfdbError(f"no object {ref!r} in {self._path}")
        return uid

    def _as_store(self, table: Any) -> Any:
        from chisurf.core.datastore import store_from_dataframe

        if hasattr(table, "n_rows"):
            return table
        return store_from_dataframe(table)

    def _describe_columns(
        self, store: Any, units: Mapping[str, str] | None, items: Mapping[str, str] | None
    ) -> None:
        """Write each column's description into the column itself.

        A column carries a name and a dtype, which is enough to read it and not
        enough to understand it: a burst duration is milliseconds and a lifetime
        is nanoseconds, and until now that was recorded only in the column name,
        when whoever wrote it remembered. ``Duration (ms)`` and ``Tau`` sit in
        the same table.

        The description travels with the column rather than with the file, so a
        column-subset read gets it too.

        Parameters
        ----------
        store : tttrlib.DataStore
        units : mapping, optional
            ``{column: unit}``. Each unit must be a ``_mmfdb_column.units``
            term; a column not named here is left without one, which means the
            unit is *unknown* rather than absent.
        items : mapping, optional
            ``{column: mmCIF item name}``, so a table can be projected onto the
            dictionary instead of matched by name.
        """
        if not units and not items:
            return
        for i in range(store.n_columns()):
            column = store[i]
            name = column.name()
            unit = (units or {}).get(name, "")
            item = (items or {}).get(name, "")
            if unit:
                _check_term(unit, _COLUMN_UNITS)
                column.set_attribute("units", unit)
            if item:
                column.set_attribute("item", item)
            if unit or item:
                column.set_attribute("name", name)

    @staticmethod
    def column_units(table: Any, name: str) -> str:
        """Return the unit a column was written with, or ``""``.

        The read half of :meth:`_describe_columns`. A unit that can be written
        and not read is a unit that only the writer believes in — and every
        consumer would otherwise be back to inferring millisecondsness from a
        column name, which is what recording it was meant to end.

        The empty string means the unit is **unknown**, not dimensionless.
        Those are different claims and a caller must be able to tell them
        apart, so a genuinely dimensionless column carries the
        ``dimensionless`` term rather than nothing.

        Parameters
        ----------
        table : tttrlib.DataStore
            A table read back from a container.
        name : str
            Column name.

        Returns
        -------
        str
            A ``_mmfdb_column.units`` term, or ``""``.
        """
        for i in range(table.n_columns()):
            column = table[i]
            if column.name() == name:
                return str(column.attribute("units") or "")
        return ""

    @staticmethod
    def column_item(table: Any, name: str) -> str:
        """Return the mmCIF item name a column was projected onto, or ``""``.

        Parameters
        ----------
        table : tttrlib.DataStore
        name : str

        Returns
        -------
        str
        """
        for i in range(table.n_columns()):
            column = table[i]
            if column.name() == name:
                return str(column.attribute("item") or "")
        return ""

    def _find_run(
        self, operation_type: str, run: str, artifact_kind: str, name: str
    ) -> int:
        """Return the UID of the same output of an earlier identical run, or 0.

        This is what makes a recomputation replace rather than accumulate — and
        the *name* is part of the identity, not decoration. One run routinely
        emits several artifacts of the same kind: an MLE fit writes one table
        per detector, all of them ``fit_result`` from one
        ``burst_lifetime_fitting`` with one settings hash. Keyed on the
        settings alone they are all "the same run", so each write replaces the
        last and a two-detector analysis ends with one table — silently, because
        replacing is the intended behaviour and nothing distinguishes it from
        the collision.
        """
        for obj in self._f.objects():
            if obj.kind != artifact_kind or obj.name != name:
                continue
            if self.tag(obj.uid, _OPERATION_TYPE) != operation_type:
                continue
            if self.tag(obj.uid, _SETTINGS_HASH) == run:
                return obj.uid
        return 0

    def _text(self, uid: int, item: str, value: str) -> None:
        if not value:
            return
        tttrlib = _tttrlib()
        tag = tttrlib.PtoTag()
        tag.name, tag.type, tag.target, tag.text = item, tttrlib.PtoType_Text, uid, str(value)
        self._f.add_tag(tag)

    def _uint(self, uid: int, item: str, value: int) -> None:
        tttrlib = _tttrlib()
        tag = tttrlib.PtoTag()
        tag.name, tag.type, tag.target, tag.u = item, tttrlib.PtoType_UInt, uid, int(value)
        self._f.add_tag(tag)

    def _ref(self, uid: int, item: str, value: int) -> None:
        tttrlib = _tttrlib()
        tag = tttrlib.PtoTag()
        tag.name, tag.type, tag.target, tag.u = item, tttrlib.PtoType_UID, uid, int(value)
        self._f.add_tag(tag)

    def _stamp_versions(self) -> None:
        """Record what a later reader needs in order to diagnose a disagreement.

        Four things drift independently — the container format, the profile,
        the dictionary and the writing application — so a file recording only
        one of them cannot be diagnosed when it disagrees with a reader.
        """
        from mmfdb.schema.pdbx_metadata import (
            extension_dictionary_hash,
            extension_dictionary_version,
        )

        self._text(0, _CONTAINER_PROFILE, PROFILE)
        self._text(0, _CONTAINER_PROFILE_VERSION, PROFILE_VERSION)
        self._uint(0, _CONTAINER_PROFILE_READ_VERSION, PROFILE_READ_VERSION)
        self._text(0, _CONTAINER_FORMAT, CONTAINER_FORMAT)
        self._text(0, _CONTAINER_FORMAT_VERSION, CONTAINER_FORMAT_VERSION)
        self._text(0, _CONTAINER_DICTIONARY_VERSION, extension_dictionary_version())
        self._text(0, _CONTAINER_DICTIONARY_HASH, extension_dictionary_hash())

    def _add_readme(self) -> int:
        """Write the plain-text preamble, before anything else.

        First on purpose. A container outlives the software that wrote it, and
        the thing a person needs when the library will not install is not a
        specification somewhere else — it is a paragraph at the start of the
        file saying what the bytes are. ASCII, so ``strings`` finds it.

        First *object*, which is not the first byte: PTO reserves space for its
        two indexes at the head of the Segment, so this begins some kilobytes
        in. Nothing can precede it without changing the container format, which
        is not ours to change.

        Returns
        -------
        int
            The object UID.
        """
        text = README.format(
            profile=PROFILE,
            profile_version=PROFILE_VERSION,
            container=CONTAINER_FORMAT,
            container_version=CONTAINER_FORMAT_VERSION,
        ).encode("ascii", "replace")
        uid = self._f.add("readme", "text", "README", text)
        if not uid:
            raise PtoMfdbError(f"could not write the preamble: {self._f.error()}")
        self._describe(
            uid,
            data_format="text",
            checksum=hashlib.sha256(text).hexdigest(),
            size_bytes=len(text),
            mime_type="text/plain; charset=us-ascii",
        )
        return uid

    def _add_instrument(
        self, raw: Path, artifact_kind: str = "tttr_photon_stream"
    ) -> int:
        """Embed the instrument file verbatim as the first object."""
        _check_term(artifact_kind, _ARTIFACT_KIND)
        checksum, size = _sha256_of_path(raw)
        data_format = _FORMAT_BY_SUFFIX.get(raw.suffix.lower(), "unknown")

        uid = self._add_payload_from_path(
            artifact_kind, data_format, raw.name, raw
        )
        self._describe(
            uid,
            data_format=data_format,
            checksum=checksum,
            size_bytes=size,
            file_path=str(raw),
        )

        tttrlib = _tttrlib()
        for suffix in _SIDECAR_SUFFIXES.get(raw.suffix.lower(), ()):
            companion = raw.with_suffix(suffix)
            if not companion.exists():
                continue
            side_sum, side_size = _sha256_of_path(companion)
            side = self._add_payload_from_path(
                "raw_data",
                _FORMAT_BY_SUFFIX.get(suffix, "unknown"),
                companion.name,
                companion,
            )
            tttrlib.pto_mark_sidecar(self._f, side, uid)
            self._describe(
                side,
                data_format=_FORMAT_BY_SUFFIX.get(suffix, "unknown"),
                checksum=side_sum,
                size_bytes=side_size,
                file_path=str(companion),
            )
        return uid

    def _add_payload_from_path(
        self, kind: str, data_format: str, name: str, path: Path
    ) -> int:
        """Add a file's bytes as an object.

        Prefers a streaming add when the library offers one. The fallback reads
        the whole file into memory, which is fine for a megabyte and wrong for
        a multi-gigabyte photon stream, so it warns rather than failing
        quietly — see the known-issues note on the streaming ``add_file``.

        Parameters
        ----------
        kind, data_format, name : str
        path : Path

        Returns
        -------
        int
            The object UID.
        """
        add_file = getattr(self._f, "add_file", None)
        if callable(add_file):
            uid = add_file(kind, data_format, name, str(path))
        else:
            size = path.stat().st_size
            if size > (256 << 20):
                warnings.warn(
                    f"{path.name} is {size / (1 << 30):.1f} GiB and tttrlib has no "
                    "streaming add_file, so it must be read into memory. See "
                    "okf/references/known-issues.md.",
                    ResourceWarning,
                    stacklevel=2,
                )
            uid = self._f.add(kind, data_format, name, path.read_bytes())
        if not uid:
            raise PtoMfdbError(f"could not embed {path}: {self._f.error()}")
        return uid

    def _describe(
        self,
        uid: int,
        *,
        data_format: str = "",
        row_grain: str = "",
        checksum: str = "",
        size_bytes: int = 0,
        mime_type: str = "",
        file_path: str = "",
        operation_type: str = "",
        parameters: Mapping[str, Any] | None = None,
        run: str = "",
        derived_from: int | Sequence[int] | None = None,
        source_row_column: str = "",
        target_row_column: str = "",
    ) -> None:
        """Attach the artifact, operation and edge rows an object stands for."""
        from mmfdb.schema.pdbx_metadata import (
            extension_dictionary_hash,
            extension_dictionary_version,
        )

        if not self.tag(uid, _ARTIFACT_ID):
            self._text(uid, _ARTIFACT_ID, str(uuid.uuid4()))
        self._text(uid, _DATA_FORMAT, data_format)
        self._text(uid, _ROW_GRAIN, row_grain)
        self._text(uid, _MIME_TYPE, mime_type)
        self._text(uid, _FILE_PATH, file_path)
        if checksum:
            self._text(uid, _CHECKSUM, checksum)
            self._text(uid, _CHECKSUM_ALGORITHM, "sha256")
        if size_bytes:
            self._uint(uid, _SIZE_BYTES, size_bytes)

        if operation_type:
            self._text(uid, _OPERATION_TYPE, operation_type)
            self._text(uid, _SETTINGS_HASH, run)
            self._text(uid, _SOFTWARE_PACKAGE, _writing_app().split()[0])
            self._text(uid, _SOFTWARE_VERSION, _writing_app().split()[-1])
            self._text(uid, _DICTIONARY_VERSION, extension_dictionary_version())
            self._text(uid, _DICTIONARY_HASH, extension_dictionary_hash())
            if parameters:
                self._text(
                    uid,
                    _SETTINGS_JSON,
                    json.dumps(dict(parameters), sort_keys=True, default=str),
                )

        for parent in _as_uids(derived_from):
            self._ref(uid, _RELATIONSHIP_TYPE, parent)
        self._text(uid, _SOURCE_ROW_COLUMN, source_row_column)
        self._text(uid, _TARGET_ROW_COLUMN, target_row_column)


def _metadata_to_cif(metadata: Mapping[str, Mapping[str, Any]]) -> str:
    """Render ``{category: {item: value}}`` as an mmCIF block.

    Every name is checked against the loaded dictionaries first. Writing an
    undeclared one would put prose in a field that looks structured, which is
    worse than leaving it out — a later reader cannot tell the two apart.

    Parameters
    ----------
    metadata : mapping
        ``{category: {item: value}}``, categories without the leading
        underscore.

    Returns
    -------
    str
        An mmCIF data block.

    Raises
    ------
    PtoMfdbError
        On an undeclared category or item.
    """
    global _VOCABULARY
    if _VOCABULARY is None:
        _VOCABULARY = _vocabulary()

    lines = ["data_measurement", "#"]
    for category, items in metadata.items():
        cat = category.lstrip("_")
        if _VOCABULARY.get_category(cat) is None:
            raise PtoMfdbError(
                f"{cat!r} is not a category in the loaded dictionaries; add it "
                "to the MMFDB extension before writing it"
            )
        for item, value in items.items():
            full = f"_{cat}.{item}"
            if _VOCABULARY.get_item(full) is None:
                raise PtoMfdbError(f"{full!r} is not a declared item")
            lines.append(f"{full}   {_cif_value(value)}")
        lines.append("#")
    return "\n".join(lines) + "\n"


def _cif_value(value: Any) -> str:
    """Quote a value the way mmCIF needs it.

    ``None`` becomes ``.`` — mmCIF's "not applicable" — rather than an empty
    string, which would read as a value that happens to be blank.
    """
    if value is None:
        return "."
    text = str(value)
    if not text:
        return "."
    if any(c in text for c in " \t'\"") or text.startswith(("_", "#", ";")):
        if "\n" in text:
            return "\n;" + text + "\n;"
        quote = "'" if '"' not in text else '"'
        return f"{quote}{text}{quote}"
    return text


def _as_uids(value: int | Sequence[int] | None) -> Iterator[int]:
    """Yield parent UIDs from a scalar, a sequence, or nothing."""
    if value is None:
        return
    if isinstance(value, int):
        if value:
            yield value
        return
    for item in value:
        if item:
            yield int(item)


def _writing_app() -> str:
    """Return ``"<package> <version>"`` for the application writing the file."""
    try:
        import chisurf

        return f"chisurf {getattr(chisurf, '__version__', 'unknown')}"
    except Exception:  # pragma: no cover - chisurf is always importable here
        return "chisurf unknown"
