"""A container ChiSurf made, extended by a writer that is not ChiSurf.

PRD-88's matrix lists ~20 writers and they are all in this tree. There is a
21st: the compiled ``tttr`` CLI writes burst tables into the same containers,
from the other repository, through the C++ half of the same profile. Nothing
tested that the two agree, and the case they have to agree on is the one PRD-88
says defects hide in — **reopen**. ChiSurf makes the container, the CLI extends
it, and every artifact must still reach the one primary.

Two failures this pins, both of which read as intact until somebody walks a
lineage:

* the CLI adding a **second** photon stream because it looked its primary up by
  name, giving the graph two roots and hanging its burst table off the root
  nothing else references;
* the two writers disagreeing about the **unit** of a column they both write,
  which is the exact failure the unit vocabulary exists to end.

Skipped, loudly, when the CLI is not built — a missing binary is a finding, not
a silent pass, so the reason says which path was looked at.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import column_names
from chisurf.core.fio.fluorescence.burst_container import units_for
from chisurf.core.fio.pto import Measurement

DATA = Path(__file__).resolve().parents[1] / "data"


def _find_tttr() -> tuple[Path | None, Path | None]:
    """The `tttr` binary and the directory holding its shared library."""
    override = os.environ.get("TTTRLIB_CLI")
    if override and os.access(override, os.X_OK):
        p = Path(override).resolve()
        return p, p.parent.parent
    root = Path(__file__).resolve().parents[2] / "modules" / "tttrlib"
    found = [c for c in (root / b / "bin" / "tttr" for b in ("build", "build_new"))
             if c.is_file() and os.access(c, os.X_OK)]
    if found:
        newest = max(found, key=lambda p: p.stat().st_mtime)
        return newest.resolve(), newest.resolve().parent.parent
    on_path = shutil.which("tttr")
    return (Path(on_path), None) if on_path else (None, None)


TTTR_BIN, LIB_DIR = _find_tttr()
SPC = DATA / "tttr" / "BH" / "132" / "BH_SPC132.spc"

pytestmark = [
    pytest.mark.skipif(
        TTTR_BIN is None,
        reason="the tttr CLI is not built; looked in modules/tttrlib/build*/bin "
               "and on PATH, and TTTRLIB_CLI is unset",
    ),
    pytest.mark.skipif(not SPC.exists(), reason="no instrument test data"),
]


def _run(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if LIB_DIR:
        for var in ("DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH"):
            env[var] = str(LIB_DIR) + os.pathsep + env.get(var, "")
    result = subprocess.run([str(TTTR_BIN), *args], capture_output=True,
                            text=True, env=env)
    assert result.returncode == 0, (
        f"tttr {' '.join(args)} exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    return result


@pytest.fixture
def setup_file(tmp_path: Path) -> Path:
    """A minimal detector setup naming the channels the fixture actually has."""
    import json

    import tttrlib

    channels = sorted({int(c) for c in np.asarray(tttrlib.TTTR(str(SPC)).routing_channel)})
    half = max(1, len(channels) // 2)
    path = tmp_path / "detector_setups.json"
    path.write_text(json.dumps({
        "last_used": "test",
        "setups": {"test": {"detectors": {
            "green": {"chs": channels[:half]},
            "red": {"chs": channels[half:] or channels[:half]},
        }}},
    }))
    return path


@pytest.fixture
def container(tmp_path: Path) -> Path:
    """A container ChiSurf created, holding only the instrument file."""
    raw = tmp_path / "m000.spc"
    shutil.copy(SPC, raw)
    for sidecar in SPC.parent.glob(SPC.stem + ".set"):
        shutil.copy(sidecar, raw.with_suffix(".set"))
    with Measurement.create(raw) as m:
        return Path(m.path)


def _extend(container: Path, raw: Path, setup: Path, min_photons: int = 20) -> None:
    _run("sm", str(raw), "--setup", str(setup),
         "--min-photons", str(min_photons), "--rate-window", "10",
         "--time-separation", "0.0005", "--output", str(container))


def test_the_cli_extends_the_container_without_adding_a_second_primary(
    container: Path, setup_file: Path
):
    raw = container.with_suffix(".spc")
    _extend(container, raw, setup_file)

    with Measurement.open(container, writable=False) as m:
        streams = [o for o in m.artifacts() if o.kind == "tttr_photon_stream"]
        assert len(streams) == 1, [o.name for o in streams]
        assert streams[0].uid == m.instrument_uid


def test_a_byte_identical_copy_under_another_name_resolves_to_the_same_primary(
    container: Path, setup_file: Path, tmp_path: Path
):
    """The lookup is on the checksum, not the file name.

    Pointing the CLI at a copy is an ordinary thing to do — a scratch directory,
    a renamed acquisition — and it must not fork the graph.
    """
    raw = container.with_suffix(".spc")
    copy = tmp_path / "some_other_name.spc"
    copy.write_bytes(raw.read_bytes())
    _extend(container, copy, setup_file)

    with Measurement.open(container, writable=False) as m:
        streams = [o for o in m.artifacts() if o.kind == "tttr_photon_stream"]
        assert len(streams) == 1, [o.name for o in streams]


def test_every_artifact_the_cli_wrote_reaches_the_primary(
    container: Path, setup_file: Path
):
    """PRD-88 rule 1, across a reopen and across the repository boundary."""
    raw = container.with_suffix(".spc")
    _extend(container, raw, setup_file)

    with Measurement.open(container, writable=False) as m:
        primary = m.instrument_uid
        assert primary
        checked = 0
        for obj in m.artifacts():
            if obj.kind in ("readme", "sample_metadata"):
                continue
            if obj.uid == primary:
                continue
            chain = [step.get("uid") for step in m.lineage(obj.uid)]
            assert primary in chain, (obj.name, chain)
            # Rule 2: an operation and its complete settings, or it only looks
            # reproducible. Rule 3: the relation is a term, not a uid.
            assert m.tag(obj.uid, "_mmfdb_operation.operation_type")
            assert m.tag(obj.uid, "_mmfdb_operation.settings_json")
            # A dictionary term, not a plausible-looking word: the assertion
            # used to accept `companion_of`, which the dictionary does not
            # define, and so accepted exactly the thing it was there to catch.
            assert m.tag(obj.uid, "_mmfdb_edge.relationship_type") in (
                "derived_from", "calibrated_by",
            )
            checked += 1
        assert checked >= 1


def test_the_two_writers_agree_on_every_column_unit(
    container: Path, setup_file: Path
):
    """One vocabulary, two implementations of the rule that reads it.

    The CLI cannot load the mmCIF dictionary, so its unit rule is a port of the
    one here. A port is only worth having if it is checked against the original.
    """
    raw = container.with_suffix(".spc")
    _extend(container, raw, setup_file)

    disagreed = []
    with Measurement.open(container, writable=False) as m:
        tables = 0
        for obj in m.artifacts():
            if obj.encoding != "dstore":
                continue
            store = m.get_store(obj.uid)
            names = list(column_names(store))
            expected = units_for({n: np.zeros(0) for n in names})
            for name in names:
                got = Measurement.column_units(store, name)
                want = expected.get(name, "")
                if got != want:
                    disagreed.append((obj.name, name, got, want))
            tables += 1
    assert tables >= 1, "the CLI wrote no table to compare"
    assert not disagreed, disagreed


def test_every_term_the_cli_writes_is_in_the_dictionary(
    container: Path, setup_file: Path
):
    """The profile defines no vocabulary of its own, so an invented word is a
    word nothing can query.

    ChiSurf's writer cannot emit one — `put_table` checks every term against the
    dictionary before writing. The CLI cannot make that check at all: it is C++,
    it does not link mmfdb, and it has no mmCIF parser. So the check has to live
    here, on the only side that can read the dictionary.

    It was worth writing. The CLI was emitting **four** undeclared terms —
    `bva`, `kde_cde`, `mle_<detector>` and `companion_of` — for operations the
    dictionary calls `burst_variance_analysis`, `burst_2cde` and
    `burst_lifetime_fitting`, and for a relation it does not define at all.
    Every container the CLI had written carried them.
    """
    from chisurf.core.fio import pto as pto_module

    raw = container.with_suffix(".spc")
    _extend(container, raw, setup_file)

    checks = (
        ("_mmfdb_operation.operation_type", pto_module._OPERATION_TYPE),
        ("_mmfdb_artifact.data_format", pto_module._DATA_FORMAT),
        ("_mmfdb_artifact.row_grain", pto_module._ROW_GRAIN),
        ("_mmfdb_edge.relationship_type", pto_module._RELATIONSHIP_TYPE),
    )
    invented = []
    with Measurement.open(container, writable=False) as m:
        for obj in m.artifacts():
            for tag, item in checks:
                value = m.tag(obj.uid, tag)
                if not value:
                    continue
                allowed = pto_module._terms(item)
                if allowed and value not in allowed:
                    invented.append((obj.name, tag, value))
    assert not invented, invented


def test_a_rerun_from_the_cli_does_not_orphan_the_companions(
    container: Path, setup_file: Path
):
    """PRD-88 rule 6. Replacing an artifact must leave its children pointing at it."""
    raw = container.with_suffix(".spc")
    _extend(container, raw, setup_file)
    _extend(container, raw, setup_file)  # identical settings -> replace in place

    with Measurement.open(container, writable=False) as m:
        searches = [o for o in m.artifacts()
                    if m.tag(o.uid, "_mmfdb_operation.operation_type") == "burst_selection"]
        assert len(searches) == 1, "a re-run with the same settings made a second artifact"
        for obj in m.artifacts():
            op = m.tag(obj.uid, "_mmfdb_operation.operation_type") or ""
            if op in ("burst_variance_analysis", "burst_2cde"):
                assert searches[0].uid in m.parents(obj.uid)
