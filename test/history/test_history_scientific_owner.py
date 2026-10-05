"""Execute history using real models and the canonical scientific owner."""

import numpy as np
import pytest

from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit
from chisurf.core.models.parse import ParseModel
from chisurf.core.project import capture_session
from chisurf.core.project.project import ResourceContext
from chisurf.core.project.transition import replace_project
from chisurf.history.core import OperationHistory
from chisurf.server.session import SessionState


def scientific_owner(tmp_path):
    """Create duplicate-named real fits with exact cross-fit parameter identity."""
    raw = tmp_path / "measurement.csv"
    raw.write_text("0,2\n1,6\n2,10\n")
    curves = [
        DataCurve(
            x=np.arange(8.0),
            y=2 + 4 * np.arange(8.0),
            ex=np.ones(8),
            ey=np.ones(8),
            name="same-data",
        )
        for _ in range(2)
    ]
    fits = [Fit(data=curve, model_class=ParseModel, name="same-fit") for curve in curves]
    for fit in fits:
        fit.model.func = "a*x+b"
        fit.model.parameters_all_dict["a"].value = 4
        fit.model.parameters_all_dict["b"].value = 2
        fit.model.update()
    fits[1].model.parameters_all_dict["a"].link = fits[0].model.parameters_all_dict["a"]
    history = OperationHistory()
    owner = SessionState(datasets=curves, fits=fits)
    owner.history = history
    owner.project_resources = ResourceContext(sources={str(raw): raw.read_bytes()})

    def capture():
        """Use the same typed codec as the project transport."""
        return capture_session(owner.datasets, owner.fits, resources=owner.project_resources)

    def publish(project):
        """Use legitimate headless-owner authorization and transactional installation."""
        return replace_project(project, owner=owner)

    return owner, history, raw, capture, publish


def test_real_owner_undo_redo_preserves_links_arrays_resources_without_source(tmp_path):
    """Scientific undo restores the original model and exact UID references."""
    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    expected = capture()
    history.configure_science(capture, publish)
    lock = history._lock
    first_uid = owner.fits[0].unique_identifier
    source_uid = owner.fits[0].model.parameters_all_dict["a"].unique_identifier
    old_source = owner.fits[0].model.parameters_all_dict["a"]
    owner.fits[0].model.parameters_all_dict["a"].value = 7
    for fit in owner.fits:
        fit.model.update()
    history.record(
        "parameter.value", "set a", {"new_value": 7}, target_uid=source_uid, persist=False
    )
    np.testing.assert_array_equal(owner.fits[1].model.y, 7 * np.arange(8.0) + 2)
    raw.unlink()
    assert history.navigate(-1)["ok"] is True
    assert history.cursor_index() == -1
    assert owner.fits[0].unique_identifier == first_uid
    assert owner.fits[0].model.parameters_all_dict["a"].unique_identifier == source_uid
    assert (
        owner.fits[1].model.parameters_all_dict["a"].link
        is owner.fits[0].model.parameters_all_dict["a"]
    )
    np.testing.assert_array_equal(owner.fits[1].model.y, 4 * np.arange(8.0) + 2)
    assert owner.project_resources.sources == expected.resources.sources
    assert history.navigate(0)["ok"] is True
    np.testing.assert_array_equal(owner.fits[1].model.y, 7 * np.arange(8.0) + 2)
    assert len(history.list_events()) == 1
    assert history._lock is lock
    from chisurf.server.services.parameters import set_parameter_value

    reply = set_parameter_value(owner, parameter_uid=source_uid, value=9.0)
    assert reply["ok"] is True
    assert owner.fits[0].model.parameters_all_dict["a"] is not old_source
    assert old_source.value == 7.0
    np.testing.assert_array_equal(owner.fits[0].model.y, 9 * np.arange(8.0) + 2)
    assert owner.fits[1].model.parameters_all_dict["a"].value == 9.0
    owner.fits[1].model.update()
    np.testing.assert_array_equal(owner.fits[1].model.y, 9 * np.arange(8.0) + 2)


def test_scientific_history_envelope_roundtrip_at_undone_cursor(tmp_path):
    """Persistence retains baseline, exact resources, redo state and cursor."""
    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    history.configure_science(capture, publish)
    owner.fits[0].model.parameters_all_dict["a"].value = 7
    for fit in owner.fits:
        fit.model.update()
    history.record("parameter.value", "set a", persist=False)
    history.navigate(-1)
    path = tmp_path / "scientific.jsonl"
    history.save_jsonl(path)
    fresh = OperationHistory()
    assert fresh.load_jsonl(path)["success"] is True
    assert fresh.cursor_index() == -1
    assert fresh.can_navigate(0)
    fresh.configure_science(capture, publish)
    raw.unlink()
    fresh.navigate(0)
    np.testing.assert_array_equal(owner.fits[1].model.y, 7 * np.arange(8.0) + 2)
    fresh.navigate(-1)
    np.testing.assert_array_equal(owner.fits[1].model.y, 4 * np.arange(8.0) + 2)
    state = fresh.export_state()
    state["states"][0]["state"]["project"]["fits"].clear()
    assert fresh.export_state()["states"][0]["state"]["project"]["fits"]


@pytest.mark.parametrize("damage", ["cursor", "version", "state_index", "science", "recursive"])
def test_envelope_validation_is_atomic(tmp_path, damage):
    """Invalid scientific envelope leaves all owned history state intact."""
    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    history.configure_science(capture, publish)
    history.record("fit.range.set", "range", persist=False)
    original = history.export_state()
    bad = history.export_state()
    if damage == "cursor":
        bad["cursor"] = 99
    elif damage == "version":
        bad["history_version"] = "999"
    elif damage == "state_index":
        bad["states"][0]["event_index"] = 9
    elif damage == "recursive":
        bad["baseline"]["project"]["extra"]["history_state"] = original
    else:
        bad["states"][0]["state"]["project"]["datasets"].clear()
    with pytest.raises(ValueError):
        history.import_state(bad)
    assert history.export_state() == original


def test_compaction_keeps_exact_scientific_baseline_and_rebases_cursor(tmp_path):
    """Removed event indices become an explicit restorable baseline."""
    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    history.configure_science(capture, publish)
    history.set_checkpoint_capture(lambda: {"count": len(history.list_events())})
    for value in [5, 6, 7, 8, 9]:
        owner.fits[0].model.parameters_all_dict["a"].value = value
        for fit in owner.fits:
            fit.model.update()
        history.record("parameter.value", str(value), persist=False)
        history.create_checkpoint(history.cursor_index())
    assert history.compact_history(keep_recent=2)["compaction_successful"] is True
    assert history.cursor_index() == 1
    assert len(history.list_events()) == 2
    assert history.get_checkpoint_before(0)["event_index"] == 0
    history.navigate(-1)
    np.testing.assert_array_equal(owner.fits[1].model.y, 7 * np.arange(8.0) + 2)
    history.navigate(1)
    np.testing.assert_array_equal(owner.fits[1].model.y, 9 * np.arange(8.0) + 2)
    history.navigate(-1)
    before = history.export_state()
    assert history.compact_history(keep_recent=1)["compaction_successful"] is False
    assert history.export_state() == before


def test_staged_edit_branches_only_after_science_and_presentation_ack(tmp_path):
    """A failed staged edit preserves redo, science identities and the cursor."""
    from chisurf.core.project.transition import PreparedPresentation

    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    reject = [False]
    views = ["original"]

    def publication(project):
        """Exercise the actual owner transaction with a failing reversible view."""
        original = list(views)

        def present(uids, ui):
            """Retain old view state until synchronous publication is accepted."""

            def commit():
                """Inject rendering failure at the real acknowledgement boundary."""
                views[:] = uids
                if reject[0]:
                    raise RuntimeError("render failed")

            return PreparedPresentation(
                commit=commit, rollback=lambda: views.__setitem__(slice(None), original)
            )

        return replace_project(project, owner=owner, present=present)

    history.configure_science(capture, publication)

    def change_to(value):
        """Mutate detached science, leaving current owner objects untouched."""

        def edit(session):
            """Apply a UID-preserving scientific edit to staged fits."""
            session.fits[0].model.parameters_all_dict["a"].value = value
            for fit in session.fits:
                fit.model.update()

        return edit

    history.apply_edit(change_to(7), "parameter.value", "set a=7", persist=False)
    history.navigate(-1)
    before = history.export_state()
    old_fits, old_data = owner.fits, owner.datasets
    old_views = list(views)
    reject[0] = True
    with pytest.raises(RuntimeError, match="render failed"):
        history.apply_edit(change_to(8), "parameter.value", "rejected edit", persist=False)
    assert history.export_state() == before
    assert owner.fits is old_fits and owner.datasets is old_data
    assert views == old_views
    np.testing.assert_array_equal(owner.fits[1].model.y, 4 * np.arange(8.0) + 2)
    reject[0] = False
    history.apply_edit(change_to(9), "parameter.value", "new branch", persist=False)
    assert history.cursor_index() == 0
    assert [row["summary"] for row in history.list_events()] == ["new branch"]
    history.navigate(-1)
    history.navigate(0)
    np.testing.assert_array_equal(owner.fits[1].model.y, 9 * np.arange(8.0) + 2)


def test_clear_starts_new_scientific_baseline_before_next_edit(tmp_path):
    """Clearing audit rows retains the exact current science as the new baseline."""
    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    history.configure_science(capture, publish)
    history.record("fit.range.set", "old event", persist=False)
    history.clear()
    assert history.list_events() == []
    assert history.can_navigate(-1)

    def edit(session):
        """Apply a later edit after the clear boundary."""
        session.fits[0].model.parameters_all_dict["a"].value = 8
        for fit in session.fits:
            fit.model.update()

    history.apply_edit(edit, "parameter.value", "after clear", persist=False)
    history.navigate(-1)
    np.testing.assert_array_equal(owner.fits[1].model.y, 4 * np.arange(8.0) + 2)


def test_canonical_history_restores_bounds_fixed_unlink_config_and_ranges(tmp_path):
    """Whole typed model state moves together with scientific ranges and links."""
    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    history.configure_science(capture, publish)
    source = owner.fits[0].model.parameters_all_dict["a"].unique_identifier
    target = owner.fits[1].model.parameters_all_dict["a"].unique_identifier

    def edit(session):
        """Edit the duplicate-named target using exact UID-bearing fit objects."""
        first, second = session.fits
        second.model.parameters_all_dict["a"].link = None
        second.model.parameters_all_dict["a"].value = 8
        second.model.parameters_all_dict["a"].fixed = True
        second.model.parameters_all_dict["a"].bounds = (-2.0, float("inf"))
        second.model.parameters_all_dict["a"].bounds_on = False
        second.fit_range = (2, 7)
        second.model.func = "a*x+b+1"
        # The direct equation edit creates its own coefficients. History must
        # restore those recorded identities, never invent another set on redo.
        second.model.parameters_all_dict["a"].value = 8
        second.model.parameters_all_dict["b"].value = 2
        second.model.parameters_all_dict["a"].fixed = True
        second.model.parameters_all_dict["a"].bounds = (-2.0, float("inf"))
        second.model.parameters_all_dict["a"].bounds_on = False
        first.model.update()
        second.model.update()

    history.apply_edit(edit, "model.update", "equation, unlink, bounds and range", persist=False)
    edited_target = owner.fits[1].model.parameters_all_dict["a"].unique_identifier
    after = capture()
    raw.unlink()
    history.navigate(-1)
    assert (
        owner.fits[1].model.parameters_all_dict["a"].link
        is owner.fits[0].model.parameters_all_dict["a"]
    )
    assert owner.fits[0].model.parameters_all_dict["a"].unique_identifier == source
    assert owner.fits[1].model.parameters_all_dict["a"].unique_identifier == target
    assert owner.fits[1].model.func == "a*x+b"
    history.navigate(0)
    second = owner.fits[1]
    assert second.model.parameters_all_dict["a"].unique_identifier == edited_target
    assert second.model.parameters_all_dict["a"].link is None
    assert second.model.parameters_all_dict["a"].fixed is True
    assert (second.model.parameters_all_dict["a"].lb, second.model.parameters_all_dict["a"].ub) == (
        -2.0,
        float("inf"),
    )
    assert second.model.parameters_all_dict["a"].bounds_on is False
    assert second.fit_range == (2, 7)
    assert second.model.func == "a*x+b+1"
    np.testing.assert_array_equal(second.model.y, 8 * np.arange(8.0) + 3)
    assert capture().parameters == after.parameters


def test_dataset_group_and_fit_removal_undo_keeps_original_arrays_and_uids(tmp_path):
    """Entity removal is reversible without source reads or UID regeneration."""
    from chisurf.core.data import DataCurveGroup

    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    group = DataCurveGroup(owner.datasets, name="same-data", unique_identifier="exact-group")
    group.current_dataset = 1
    owner.datasets = [group]
    expected = capture()
    history.configure_science(capture, publish)

    def remove(session):
        """Remove the owned group and its cross-linked fits as one valid edit."""
        session.fits.clear()
        session.datasets.clear()

    history.apply_edit(remove, "dataset.remove", "Remove measurement group and fits", persist=False)
    assert owner.datasets == [] and owner.fits == []

    raw.unlink()
    history.navigate(-1)
    restored = owner.datasets[0]
    assert restored.unique_identifier == "exact-group"
    assert restored._current_dataset == 1
    assert restored.current_dataset is restored[1]
    assert len(restored) == 2
    assert [curve.unique_identifier for curve in restored] == list(expected.datasets)
    assert [fit.unique_identifier for fit in owner.fits] == [row["uid"] for row in expected.fits]
    assert (
        owner.fits[1].model.parameters_all_dict["a"].link
        is owner.fits[0].model.parameters_all_dict["a"]
    )
    np.testing.assert_array_equal(restored[1].y, 2 + 4 * np.arange(8.0))
    assert owner.project_resources.sources == expected.resources.sources
    history.navigate(0)
    assert owner.datasets == [] and owner.fits == []


def test_audit_record_after_undo_does_not_erase_scientific_redo(tmp_path):
    """Only a successful scientific change truncates the redo branch."""
    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    history.configure_science(capture, publish)
    owner.fits[0].model.parameters_all_dict["a"].value = 7
    for fit in owner.fits:
        fit.model.update()
    changed = history.record("parameter.value", "set a", persist=False)
    history.navigate(-1)
    history.record("console.run", "inspect without editing", persist=False)
    assert [row["summary"] for row in history.list_events()] == ["inspect without editing", "set a"]
    assert history.list_events()[1]["event_id"] == changed["event_id"]
    assert history.cursor_index() == 0
    history.navigate(1)
    np.testing.assert_array_equal(owner.fits[1].model.y, 7 * np.arange(8.0) + 2)


def test_edit_history_validation_finishes_before_irreversible_owner_ack(tmp_path, monkeypatch):
    """History publication cannot discover a validation fault after owner commit."""
    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    acknowledged = [False]
    original = history.validate_state

    def validate(state):
        """Reject validation that incorrectly occurs after science publication."""
        if acknowledged[0]:
            raise RuntimeError("validation after acknowledged owner commit")
        return original(state)

    def publication(project):
        """Acknowledge only a completed real canonical owner transaction."""
        result = publish(project)
        acknowledged[0] = True
        return result

    history.configure_science(capture, publication)
    monkeypatch.setattr(history, "validate_state", validate)

    def edit(session):
        """Apply a detached scientific coefficient change."""
        session.fits[0].model.parameters_all_dict["a"].value = 7
        for fit in session.fits:
            fit.model.update()

    history.apply_edit(edit, "parameter.value", "staged validation", persist=False)
    assert history.cursor_index() == 0
    np.testing.assert_array_equal(owner.fits[1].model.y, 7 * np.arange(8.0) + 2)


def test_navigation_carries_complete_target_cursor_envelope_to_owner(tmp_path):
    """Owner policy can authorize the exact scientific target and durable cursor."""
    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    seen = []

    def publication(project):
        """Read the same typed envelope the owner must validate and install."""
        state = project.extra["history_state"]
        seen.append(state["cursor"])
        history.validate_state(state)
        return publish(project)

    history.configure_science(capture, publication)
    history.record("fit.range.set", "state", persist=False)
    history.navigate(-1)
    history.navigate(0)
    assert seen == [-1, 0]


def test_invalid_scientific_capture_never_truncates_a_redo_branch(tmp_path):
    """Canonical type alone is insufficient; the whole scientific graph must validate."""
    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    history.configure_science(capture, publish)
    history.record("fit.range.set", "valid", persist=False)
    history.navigate(-1)
    original = history.export_state()
    broken = capture()
    next(iter(broken.datasets.values()))["arrays"]["y"]["values"] = [1.0]
    history.configure_science(lambda: broken, publish)
    with pytest.raises(ValueError):
        history.record("model.update", "bad snapshot", persist=False)
    assert history.export_state() == original


def test_audit_append_cannot_break_scientific_cursor_continuity(tmp_path):
    """Audit-only transport rows cannot silently extend a scientific timeline."""
    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    history.configure_science(capture, publish)
    history.record("fit.range.set", "current science", persist=False)
    original = history.export_state()
    row = OperationHistory().record("audit", "external audit row", persist=False)
    with pytest.raises(ValueError, match="audit"):
        history.load_events([row], replace=False)
    assert history.export_state() == original
