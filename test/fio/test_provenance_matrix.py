"""Every artifact reaches the primary data — across sources, and at depth.

[PRD-88](/prds/prd-88.md) exists because this was being tested on **one
synthetic two-step chain**, and an hour of driving the real writers found 6 of
26 artifacts with a broken lineage. Four of the six were one root cause, and it
only showed on **reopen**: a writer that creates the container in the same call
has the uid from ``create`` and never asks again.

This is the matrix half. Two axes, and the second is the one with no coverage
at all:

* **Sources** — what a container can be *about*. A photon stream, a photon
  stream with a sidecar its reader cannot do without, and a source that is not
  photons (the cell that broke: ``create`` takes an ``artifact_kind`` precisely
  so a binned trace is not called a photon stream).
* **Nested chains** — depth, fan-in, siblings, a second relation type, and
  extend-after-reopen. Every case tested before this was one or two steps, and
  the interesting failures are not there.

The rules being pinned are PRD-88's own, and they are about the graph rather
than about any writer: every artifact reaches the primary or *is* primary; every
derived artifact names its operation and its complete settings; the relation is
a term; a fan-in keeps every parent; a chain survives a reopen; a re-run orphans
nothing; the walk terminates.

Deliberately driven through the real container writer rather than by
synthesising tags — a test that builds the graph by hand records what the test
author believes rather than what the code does, which is exactly how the found
defect survived.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.fio.pto import Measurement

DATA = Path(__file__).resolve().parents[1] / "data"
PTU = DATA / "clsm" / "Leica_SP5.ptu"
SPC = DATA / "tttr" / "BH" / "132" / "BH_SPC132.spc"

pytestmark = pytest.mark.skipif(not PTU.exists(), reason="no instrument test data")


def _rows(n: int, **extra) -> dict:
    out = {
        "Number of Photons": np.arange(n, dtype=np.int64),
        "Mean Macro Time (ms)": np.linspace(0.0, 100.0, n),
    }
    out.update(extra)
    return out


def _walk_every_artifact(path: Path) -> list[str]:
    """Return one complaint per artifact that breaks a rule. Empty is passing.

    Collects rather than asserts, so one run says everything that is wrong with
    a container instead of the first thing.
    """
    problems: list[str] = []
    with Measurement.open(path, writable=False) as m:
        primaries = set(m.instrument_uids)
        for obj in m.artifacts():
            if obj.kind in ("readme", "sample_metadata"):
                continue
            where = f"{obj.name!r} ({obj.kind})"
            if obj.uid in primaries:
                continue
            if not primaries:
                problems.append(f"{where}: the container has no primary at all")
                continue

            chain = [step.get("uid") for step in m.lineage(obj.uid)]
            # Rule 7: the walk terminates and does not revisit.
            if len(chain) != len(set(chain)):
                problems.append(f"{where}: lineage repeats an object")
            # Rule 1: reaches the primary data.
            if not (primaries & set(chain)):
                problems.append(f"{where}: never reaches the primary; chain={chain}")
            # Rule 2: names its operation and its complete settings.
            if not m.tag(obj.uid, "_mmfdb_operation.operation_type"):
                problems.append(f"{where}: no operation_type")
            if not m.tag(obj.uid, "_mmfdb_operation.settings_json"):
                problems.append(f"{where}: no settings_json")
            # Rule 3: the relation is a term, not a uid and not empty.
            rel = m.tag(obj.uid, "_mmfdb_edge.relationship_type")
            if rel not in ("derived_from", "calibrated_by"):
                problems.append(f"{where}: relationship_type is {rel!r}")
            if not m.parents(obj.uid):
                problems.append(f"{where}: records no parent")
    return problems


# -- the source axis -------------------------------------------------------------


def test_a_photon_stream_source_reconstructs(tmp_path: Path):
    raw = tmp_path / "m000.ptu"
    shutil.copy(PTU, raw)
    with Measurement.create(raw) as m:
        container = Path(m.path)
        m.put_table(
            "bursts",
            _rows(8),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"L": 20},
            derived_from=m.instrument_uids,
        )
    assert _walk_every_artifact(container) == []


@pytest.mark.skipif(not SPC.exists(), reason="no B&H test data")
def test_a_source_that_carries_a_sidecar_reconstructs(tmp_path: Path):
    """A `.spc` keeps half its header in a `.set`, so the sidecar is in the graph."""
    raw = tmp_path / "m000.spc"
    shutil.copy(SPC, raw)
    for candidate in SPC.parent.glob("*.set"):
        shutil.copy(candidate, raw.with_suffix(".set"))

    with Measurement.create(raw) as m:
        container = Path(m.path)
        m.put_table(
            "bursts",
            _rows(8),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"L": 20},
            derived_from=m.instrument_uids,
        )
    assert _walk_every_artifact(container) == []


def test_a_source_that_is_not_photons_reconstructs(tmp_path: Path):
    """The cell that broke.

    ebFRET starts from binned traces, and calling those a photon stream would be
    a statement about the file that is false in the one field a reader consults
    to decide how to open it. `create` takes an `artifact_kind` for exactly this,
    and the primary was once recovered on reopen by matching *one* kind — so a
    container like this came back with no primary, a writer passing
    `derived_from=()` then recorded no parent, and everything after it chained to
    a sibling.
    """
    raw = tmp_path / "traces.dat"
    raw.write_text("\n".join(f"{i}\t{i * 2}" for i in range(64)))

    with Measurement.create(raw, artifact_kind="trace_data") as m:
        container = Path(m.path)

    # Reopened, which is the half that failed: a *second* analysis on the same
    # measurement never sees the uid that `create` returned.
    with Measurement.open(container, writable=True) as m:
        assert m.instrument_uid, "reopening lost the primary"
        m.put_table(
            "states",
            _rows(6),
            artifact_kind="analysis_result",
            operation_type="photon_hmm",
            row_grain="state",
            parameters={"n_states": 2},
            derived_from=m.instrument_uids,
        )
    assert _walk_every_artifact(container) == []


def test_a_container_with_no_primary_is_reported_not_guessed(tmp_path: Path):
    """PRD-88's open decision, pinned as *behaviour* rather than left implicit.

    A curve typed in or computed from a model genuinely has no measurement
    behind it. Today "legitimately primary" and "lost its parent" look identical,
    which is the thing PRD-88 says must not stay true — so this records what the
    code currently does, and will fail the moment somebody changes it, which is
    when the decision gets made rather than absorbed.
    """
    container = tmp_path / "empty.pto"
    with Measurement.create_empty(container) as m:
        m.put_curve(
            "model",
            np.arange(8.0),
            np.arange(8.0),
            artifact_kind="decay",
            operation_type="fitting",
            parameters={"tau": 4.0},
        )

    with Measurement.open(container, writable=False) as m:
        assert m.instrument_uids == [], "expected no primary"
    # The walk reports it rather than passing silently.
    problems = _walk_every_artifact(container)
    assert any("no primary" in p for p in problems), problems


# -- the chain axis --------------------------------------------------------------


@pytest.fixture
def measurement(tmp_path: Path) -> Path:
    raw = tmp_path / "m000.ptu"
    shutil.copy(PTU, raw)
    with Measurement.create(raw) as m:
        return Path(m.path)


def test_a_four_deep_chain_reaches_the_photons_from_the_bottom(measurement: Path):
    """Photons -> bursts -> per-burst fit -> pooled states."""
    with Measurement.open(measurement, writable=True) as m:
        bursts = m.put_table(
            "bursts",
            _rows(12),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"L": 20},
            derived_from=m.instrument_uids,
        )
        fits = m.put_table(
            "mle",
            _rows(12, **{"Tau (green)": np.linspace(1.0, 4.0, 12)}),
            artifact_kind="burst_table",
            operation_type="burst_lifetime_fitting",
            row_grain="burst",
            parameters={"model": "fit23"},
            derived_from=[bursts],
        )
        m.put_table(
            "states",
            {"Tau (green)": np.array([1.2, 3.8])},
            artifact_kind="analysis_result",
            operation_type="photon_hmm",
            row_grain="state",
            parameters={"n_states": 2},
            derived_from=[fits],
            source_row_column="Burst",
            target_row_column="State",
        )
    assert _walk_every_artifact(measurement) == []

    with Measurement.open(measurement, writable=False) as m:
        deepest = [o for o in m.artifacts() if o.name == "states"][0]
        chain = [step.get("uid") for step in m.lineage(deepest.uid)]
        assert len(chain) >= 4, chain


def test_a_fan_in_keeps_every_parent(measurement: Path):
    """Burst fusion. The arity was unexpressible in the format this replaces,
    so there is no legacy behaviour to fall back on — rule 4.
    """
    with Measurement.open(measurement, writable=True) as m:
        left = m.put_table(
            "bursts-a",
            _rows(10),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"L": 20},
            derived_from=m.instrument_uids,
        )
        right = m.put_table(
            "bursts-b",
            _rows(10),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"L": 60},
            derived_from=m.instrument_uids,
        )
        fused = m.put_table(
            "fused",
            _rows(7),
            artifact_kind="burst_table",
            operation_type="burst_fusion",
            row_grain="burst",
            parameters={"gap_ms": 1.0},
            derived_from=[left, right],
        )
        # ...and something derived from *that*, which is where a fan-in stops
        # being a special case and becomes an ordinary parent.
        m.put_table(
            "fused-bva",
            _rows(7),
            artifact_kind="burst_table",
            operation_type="burst_variance_analysis",
            row_grain="burst",
            parameters={"slice": 5},
            derived_from=[fused],
        )

    assert _walk_every_artifact(measurement) == []
    with Measurement.open(measurement, writable=False) as m:
        obj = [o for o in m.artifacts() if o.name == "fused"][0]
        assert len(m.parents(obj.uid)) == 2, m.parents(obj.uid)


def test_siblings_on_one_parent_each_reach_the_photons(measurement: Path):
    with Measurement.open(measurement, writable=True) as m:
        bursts = m.put_table(
            "bursts",
            _rows(10),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"L": 20},
            derived_from=m.instrument_uids,
        )
        for op in (
            "burst_variance_analysis",
            "burst_2cde",
            "burst_correlation",
            "burst_lifetime_fitting",
        ):
            m.put_table(
                op,
                _rows(10),
                artifact_kind="burst_table",
                operation_type=op,
                row_grain="burst",
                parameters={"op": op},
                derived_from=[bursts],
            )
    assert _walk_every_artifact(measurement) == []


def test_a_calibration_is_a_second_relation_type(measurement: Path):
    """`calibrated_by`, not `derived_from` — the background an MLE was run
    against is an input, and saying so is the whole point of a typed edge.
    """
    with Measurement.open(measurement, writable=True) as m:
        background = m.put_table(
            "background",
            {"counts": np.arange(16.0)},
            artifact_kind="decay",
            operation_type="background_correction",
            row_grain="curve_point",
            parameters={"window_ms": 1.0},
            derived_from=m.instrument_uids,
        )
        bursts = m.put_table(
            "bursts",
            _rows(10),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"L": 20},
            derived_from=m.instrument_uids,
        )
        m.put_table(
            "mle",
            _rows(10),
            artifact_kind="burst_table",
            operation_type="burst_lifetime_fitting",
            row_grain="burst",
            parameters={"model": "fit23"},
            derived_from=[bursts, background],
        )

    assert _walk_every_artifact(measurement) == []
    with Measurement.open(measurement, writable=False) as m:
        obj = [o for o in m.artifacts() if o.name == "mle"][0]
        assert len(m.parents(obj.uid)) == 2


def test_a_chain_extended_after_a_reopen_still_reconstructs(measurement: Path):
    """Rule 5, and the shape most of the found defects lived in.

    Three separate opens, each adding a step, because that is what a second and
    third analysis on the same measurement actually do.
    """
    with Measurement.open(measurement, writable=True) as m:
        m.put_table(
            "bursts",
            _rows(10),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"L": 20},
            derived_from=m.instrument_uids,
        )

    with Measurement.open(measurement, writable=True) as m:
        bursts = [o for o in m.artifacts() if o.name == "bursts"][0]
        m.put_table(
            "bva",
            _rows(10),
            artifact_kind="burst_table",
            operation_type="burst_variance_analysis",
            row_grain="burst",
            parameters={"slice": 5},
            derived_from=[bursts.uid],
        )

    with Measurement.open(measurement, writable=True) as m:
        bva = [o for o in m.artifacts() if o.name == "bva"][0]
        m.put_table(
            "bva-filtered",
            _rows(4),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"std_max": 0.2},
            derived_from=[bva.uid],
        )

    assert _walk_every_artifact(measurement) == []


def test_a_rerun_does_not_orphan_what_was_derived_from_it(measurement: Path):
    """Rule 6. Replacing an artifact in place must leave its children on it."""
    with Measurement.open(measurement, writable=True) as m:
        bursts = m.put_table(
            "bursts",
            _rows(10),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"L": 20},
            derived_from=m.instrument_uids,
        )
        m.put_table(
            "bva",
            _rows(10),
            artifact_kind="burst_table",
            operation_type="burst_variance_analysis",
            row_grain="burst",
            parameters={"slice": 5},
            derived_from=[bursts],
        )

    with Measurement.open(measurement, writable=True) as m:
        again = m.put_table(
            "bursts",
            _rows(10),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"L": 20},
            derived_from=m.instrument_uids,
        )
        assert again == bursts, "same settings must replace in place"

    assert _walk_every_artifact(measurement) == []
    with Measurement.open(measurement, writable=False) as m:
        child = [o for o in m.artifacts() if o.name == "bva"][0]
        assert bursts in m.parents(child.uid), "the re-run orphaned its child"


def test_a_re_analysis_does_not_claim_its_source_twice(measurement: Path):
    """Tags are appended, so a container analysed three times once claimed the
    same source four times. An edge recorded twice is not truer.
    """
    for _ in range(3):
        with Measurement.open(measurement, writable=True) as m:
            m.put_table(
                "bursts",
                _rows(10),
                artifact_kind="burst_table",
                operation_type="burst_selection",
                row_grain="burst",
                parameters={"L": 20},
                derived_from=m.instrument_uids,
            )

    with Measurement.open(measurement, writable=False) as m:
        obj = [o for o in m.artifacts() if o.name == "bursts"][0]
        parents = m.parents(obj.uid)
        assert len(parents) == len(set(parents)), parents
        assert len(parents) == len(m.instrument_uids), parents
