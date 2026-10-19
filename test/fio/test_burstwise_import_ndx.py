"""A container the importer writes must open in ndX.

The importer is the writing end of a pipeline whose reading end is ndX's
`.pto` reader. If the tables carry the wrong operation terms, ndX finds
nothing to show — an error that surfaces as absence, not as a message, and
exactly the kind that ships silently. This pins the round trip: the burst
list must be found as a burst search, its lifetime companions joined on
rows, and the raw stream named in provenance.
"""

from __future__ import annotations

import pathlib
import shutil

import pytest

from chisurf.core.fio.fluorescence.burstwise_import import convert_folder, scan_folder

pytest.importorskip("ndxplorer.io.pto_reader")

from ndxplorer.io.pto_reader import list_tables, read_container  # noqa: E402

SAMPLE = (
    pathlib.Path.home()
    / ".hermes"
    / "cache"
    / "scratch"
    / "burstwise_samples"
    / "burstwise_All 0.1066#60"
)
TTTR = (
    pathlib.Path(__file__).resolve().parents[2]
    / "test"
    / "data"
    / "clsm"
    / "Leica_SP5.ptu"
)

pytestmark = pytest.mark.skipif(
    not SAMPLE.is_dir() or not TTTR.is_file(), reason="sample folder or TTTR fixture missing"
)


@pytest.fixture()
def container(tmp_path: pathlib.Path) -> pathlib.Path:
    """One-stem copy of the real sample with a stand-in TTTR beside it."""
    stem = "Split_44_132_75murea_sm-0000"
    day = tmp_path / "exp"
    work = day / "burstwise_All 0.1066#60"
    for sub, pat in (
        ("bi4_bur", "*.bur"),
        ("bg4", "*.bg4"),
        ("br4", "*.br4"),
        ("BIDs", "*.bst"),
    ):
        (work / sub).mkdir(parents=True)
        src = next(iter(sorted((SAMPLE / sub).glob("*-0000*"))))
        shutil.copy(src, work / sub / src.name)
    shutil.copytree(SAMPLE / "Info", work / "Info")
    shutil.copy(TTTR, day / f"{stem}.ht3")

    out = tmp_path / "pto"
    report = convert_folder(work, source_resolver=lambda s, m: day / f"{s}.ht3", out_dir=out)
    assert report.containers, "conversion wrote nothing"
    return pathlib.Path(report.containers[0])


def test_sidecar_mode_writes_analysis_only_container(tmp_path: pathlib.Path):
    """Deposition layout: raw stays beside a small analysis-only container.

    One container per MEASUREMENT: the container is named after the
    measurement folder, references every analyzed raw as a sidecar (sha256,
    size, name), and ndX still finds the bursts — the tables, not the
    photons, are what it reads.
    """
    import hashlib

    import tttrlib

    from chisurf.plugins.burst.burstwise_import.api import ImportSettings, import_folder

    stem = "Split_44_132_75murea_sm-0000"
    day = tmp_path / "exp"
    work = day / "burstwise_All 0.1066#60"
    for sub in ("bi4_bur", "bg4", "br4", "BIDs"):
        (work / sub).mkdir(parents=True)
        src = next(iter(sorted((SAMPLE / sub).glob("*-0000*"))))
        shutil.copy(src, work / sub / src.name)
    shutil.copytree(SAMPLE / "Info", work / "Info")
    raw = day / f"{stem}.ht3"
    shutil.copy(TTTR, raw)

    out = tmp_path / "pto"
    report = import_folder(
        work, ImportSettings(source_mode="beside", raw_data="sidecar", out_dir=out)
    )
    pto = pathlib.Path(report.containers[0])
    assert pto.name == "exp.mmfdb.pto"  # one container per measurement
    assert len(report.containers) == 1

    # analysis-only: kilobytes, not the megabytes of the embedded stream
    assert pto.stat().st_size < 1_000_000
    assert raw.is_file()  # the raw data stays beside the container

    f = tttrlib.PtoFile()
    f.open(str(pto))
    try:
        name = tttrlib.pto_tag(f, 0, "_mmfdb_sidecar.0.name")
        checksum = tttrlib.pto_tag(f, 0, "_mmfdb_sidecar.0.checksum")
        size = int(tttrlib.pto_tag(f, 0, "_mmfdb_sidecar.0.size_bytes"))
    finally:
        f.close()
    assert name == raw.name
    assert checksum == hashlib.sha256(raw.read_bytes()).hexdigest()
    assert size == raw.stat().st_size

    # ndX still reads the analysis
    assert read_container(pto).size > 0


def test_sidecar_container_beside_its_raws_records_no_local_path(tmp_path: pathlib.Path):
    """A container written beside its raws links them by relative name only.

    The record travels as a folder, so a sidecar link must resolve wherever
    the folder lands -- and must not leak the writer's absolute path into a
    public deposition. The raw's own `file_path` tag once overwrote the
    relative link with the absolute path.
    """
    import tttrlib

    from chisurf.plugins.burst.burstwise_import.api import ImportSettings, import_folder

    stem = "Split_44_132_75murea_sm-0000"
    day = tmp_path / "exp"
    work = day / "burstwise_All 0.1066#60"
    for sub in ("bi4_bur", "bg4", "br4", "BIDs"):
        (work / sub).mkdir(parents=True)
        src = next(iter(sorted((SAMPLE / sub).glob("*-0000*"))))
        shutil.copy(src, work / sub / src.name)
    shutil.copytree(SAMPLE / "Info", work / "Info")
    raw = day / f"{stem}.ht3"
    shutil.copy(TTTR, raw)

    report = import_folder(
        work, ImportSettings(source_mode="beside", raw_data="sidecar", out_dir=day)
    )
    pto = pathlib.Path(report.containers[0])
    assert pto.parent == day

    assert str(tmp_path).encode() not in pto.read_bytes()
    f = tttrlib.PtoFile()
    f.open(str(pto))
    try:
        assert tttrlib.pto_tag(f, 0, "_mmfdb_sidecar.0.path") == raw.name
        links = [tttrlib.pto_tag(f, o.uid, "_mmfdb_artifact.file_path") for o in f.objects()]
    finally:
        f.close()
    assert raw.name in links


def test_burst_table_is_found_as_a_burst_search(container: pathlib.Path):
    tables = list_tables(container)
    assert len(tables) == 1
    entry = tables[0]
    assert entry["operation"] == "burst_selection"
    assert entry["grain"] == "burst"
    assert entry["rows"] > 0


def test_companions_are_joined_and_source_named(container: pathlib.Path):
    ds = read_container(container)
    assert ds.size > 0
    names = {str(n) for n in ds.store.column_names()}
    # burst table columns
    assert "Number of Photons" in names
    # the MLE lifetime fits joined as companions
    assert "Tau (green)" in names
    assert "Tau  (red)" in names  # legacy spelling kept verbatim (unmapped)
    provenance = getattr(ds, "provenance", {})
    ops = {a["operation_type"] for a in provenance.get("artifacts", {}).values()}
    assert ops == {"burst_selection", "burst_lifetime_fitting"}
    sources = [s["name"] for s in provenance.get("sources", [])]
    assert any("Split_44_132_75murea_sm-0000" in s for s in sources)


def test_instrument_files_are_stored_under_the_reader_that_reads_them(tmp_path: pathlib.Path):
    """The object's encoding is the tttrlib container; data_format the dictionary term.

    An .ht3 used to be stored as "ptu" -- and tttrlib,
    which picks its reader from the encoding, handed it to the PTU reader. A B&H
    .spc is decided from the module and ADC its .set names.
    """
    from chisurf.core.fio.pto import _FORMAT_BY_SUFFIX, _encoding_for, _format_term

    ht3 = tmp_path / "a.ht3"
    ht3.write_bytes(b"x")
    assert _encoding_for(ht3) == "ht3" and _FORMAT_BY_SUFFIX[".ht3"] == "ht3"
    for module, adc, want in (("SPC-630", "8 bits ADC", "spc-600_256"),
                              ("SPC-630", "12 bits ADC", "spc-600_4096"),
                              ("SPC-830", "12 bits ADC", "spc-130")):
        spc = tmp_path / f"{module}_{adc[:2].strip()}.spc"
        spc.write_bytes(b"x")
        spc.with_suffix(".set").write_text(
            f"*IDENTIFICATION\n  Revision  : {adc}\n  Contents  : Setup file made by system "
            f"at the end of FIFO measurement\n with module {module} (Ser.No. 3A0132)\n")
        assert _encoding_for(spc) == want, (module, adc)
        assert _format_term(spc) == want.replace("-", "_")  # the dictionary's spelling
    # one .set per acquisition: the rollover files without their own take it
    run = tmp_path / "run"
    run.mkdir()
    (run / "m_000.spc").write_bytes(b"x")
    (run / "m_001.spc").write_bytes(b"x")
    (run / "m_001.set").write_text("Revision  : 8 bits ADC\n with module SPC-630 (Ser.No. 1)\n")
    assert _encoding_for(run / "m_000.spc") == "spc-600_256"
    alone = tmp_path / "alone"
    alone.mkdir()
    (alone / "x.spc").write_bytes(b"x")
    assert _encoding_for(alone / "x.spc") == "spc"
    assert _encoding_for(tmp_path / "m.set") == "bh"
