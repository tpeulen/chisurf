"""Prove discovery, side-effect exclusions, and subprocess failure reporting."""

import json
from types import SimpleNamespace

import pytest

from . import test_click_all_plugins as harness


def test_discovery_covers_every_gui_manifest_exactly_once():
    """Every emtk manifest is swept exactly once."""
    declared = {
        key
        for key, manifest in harness.CATALOG.items()
        if manifest.get("entrypoints", {}).get("emtk")
    }
    assert set(harness.IDS_EMTK) == declared
    assert len(harness.IDS_EMTK) > 100


@pytest.mark.parametrize(
    "name",
    [
        "open_file",
        "save",
        "delete_record",
        "oauth",
        "account",
        "connect",
        "upload",
        "acquire",
        "run_remote",
        "start_hardware",
        "Update Now",
        "User Editor",
        "Enable Python LSP",
        "Enable editor RPC",
        "×",
        "× ×",
        "＋ ＋",
        "↑ Parent",
    ],
)
def test_side_effect_actions_have_an_explicit_exclusion(name):
    """Control exclusions cover files, user accounts, jobs, and equipment."""
    assert harness.skip_reason(name)
    assert harness.skip_reason("innocent", ["hardware"])
    assert harness.skip_reason("innocent", ["modal"])
    assert harness.skip_reason("Gain") is None


def test_bounded_job_operates_real_cancel_and_checks_idle(tmp_path, monkeypatch):
    """A slow local calculation may pass when its real cancellation restores idle."""
    monkeypatch.setenv("CHISURF_E2E_DIR", str(tmp_path))
    recorder = SimpleNamespace(rows=[])
    idle = False

    def settle(timeout):
        """Represent the job's pending and then cancelled state."""
        if not idle:
            raise TimeoutError()
        return "idle"

    def frame():
        """Expose the actual cancellation control on the busy frame."""
        recorder.rows.append(
            {"id": "Cancel##cancel", "kind": "button", "enabled": True, "rect": (1, 1, 10, 10)}
        )

    def click(rect):
        """Only a real click, rather than private job state mutation, cancels it."""
        nonlocal idle
        idle = True

    driver = SimpleNamespace(settle=settle, frame=frame, click=click)
    result = {"plugin": "fixture", "current_control": "Calculate"}
    assert harness.settle_with_cancel(driver, recorder, result) == "idle"
    assert result["job_cancellations"][0]["cancel_control"] == "Cancel##cancel"


def test_tags_and_nested_choices_are_read_from_the_actual_spec():
    """Metadata is considered even when the visible caption sounds safe."""
    spec = {
        "sections": [
            {
                "type": "panel",
                "sections": [
                    {
                        "type": "button_row",
                        "buttons": [{"action": "proceed", "tags": ["external"]}],
                    },
                    {"type": "choice", "attr": "mode"},
                ],
            }
        ]
    }
    assert harness.control_tags(spec, "Proceed##proceed") == {"external"}
    assert [s["attr"] for s in harness.walk(spec) if s["type"] == "choice"] == ["mode"]


def test_tour_owner_adapters_preserve_real_tours():
    """Existing guide aliases and header-editor composition are supported."""
    tour = SimpleNamespace(start=lambda: None, next=lambda: None, stop=lambda: None)
    for app in (
        SimpleNamespace(tour=tour),
        SimpleNamespace(guide=tour),
        SimpleNamespace(header_gui=SimpleNamespace(tour=tour)),
        SimpleNamespace(phasor_gui=SimpleNamespace(tour=tour)),
    ):
        assert harness.tour_for(app) is tour
    assert harness.tour_for(SimpleNamespace()) is None


def test_worker_crash_cannot_reuse_an_earlier_passing_result(tmp_path, monkeypatch):
    """A stale JSON artifact must never turn a crash into a passing plugin."""
    monkeypatch.setenv("CHISURF_E2E_DIR", str(tmp_path))
    path = tmp_path / "example.json"
    path.write_text(json.dumps({"status": "passed"}))
    monkeypatch.setattr(
        harness.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=-11, stdout="", stderr="native crash"),
    )
    with pytest.raises(AssertionError, match="worker exit -11"):
        harness._isolated("example", "emtk")
    assert json.loads(path.read_text())["status"] != "passed"
    assert (tmp_path / "example.log").read_text() == "native crash"


def test_worker_timeout_is_an_explicit_failure_artifact(tmp_path, monkeypatch):
    """A stuck plugin reports its bounded timeout instead of a test skip."""
    monkeypatch.setenv("CHISURF_E2E_DIR", str(tmp_path))
    monkeypatch.setenv("CHISURF_E2E_TIMEOUT", "2")

    def timeout(*args, **kwargs):
        """Pretend the isolated worker did not complete."""
        raise harness.subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(harness.subprocess, "run", timeout)
    with pytest.raises(pytest.fail.Exception, match="exceeded 2s"):
        harness._isolated("example", "emtk")
    assert json.loads((tmp_path / "example.json").read_text())["errors"] == ["worker exceeded 2s"]


def test_native_scenario_visits_each_tab_and_keeps_expanded_children_reachable(
    tmp_path, monkeypatch
):
    """A tab switch or header click must not silently hide untested safe actions."""
    from emtk import im
    from emtk.app import ImApp

    import chisurf.emtk.plugins
    from chisurf.emtk.help_guide import EmTkGuidedTour

    used = []

    def gui():
        """Draw two real tabs with actions sorting after their tab captions."""
        if im.begin_tab_bar("pages"):
            for title in ("Alpha", "Beta"):
                selected = im.begin_tab_item(title)
                im.set_item_tooltip("Select this page.")
                if selected:
                    im.push_id(title)
                    expanded = im.collapsing_header(f"Group {title}")
                    im.set_item_tooltip("Show this page's actions.")
                    if expanded:
                        if im.button("Gain"):
                            used.append(title)
                            app.tour.notify_used("gain")
                        im.set_item_tooltip("Perform an in-memory unit-test action.")
                        app.remember("gain")
                    im.pop_id()
                    im.end_tab_item()
            im.end_tab_bar()

    app = ImApp(gui)
    app.tour = EmTkGuidedTour(
        [
            {"title": "First", "text": "First step."},
            {"title": "Gain", "target": "gain", "await": True},
        ],
        wait_for_controls=True,
    )
    monkeypatch.setattr(chisurf.emtk.plugins, "load_plugin", lambda *a, **k: app)
    monkeypatch.setattr(harness, "SIZE", (420, 320))
    monkeypatch.setenv("CHISURF_E2E_DIR", str(tmp_path))
    result = {
        "plugin": "fixture",
        "clicked": [],
        "skipped": [],
        "combos": [],
        "tabs": [],
        "dialogs_closed": 0,
        "errors": [],
    }
    harness._native("fixture", result, tmp_path / "fixture.png")
    assert used[:2] == ["Alpha", "Beta"] and len(used) == 3
    assert set(result["tabs"]) == {"Alpha", "Beta"}
    assert result["clicked"].count("Gain") == 2
    assert len([key for key in result["clicked_ids"] if "Gain" in key]) == 2
    assert not result["errors"]
    assert result["tour_indices"] == [0, 1]


def test_tour_next_cannot_report_progress_while_awaiting(tmp_path):
    """Await remains unsatisfied until a real target interaction notifies the tour."""
    from chisurf.emtk.help_guide import EmTkGuidedTour

    tour = EmTkGuidedTour(
        [{"title": "Click", "target": "confirm", "await": True}, {"title": "Done"}],
        wait_for_controls=True,
    )
    tour.start()
    calls = []
    driver = SimpleNamespace(
        rect=lambda _: (1, 1, 10, 10),
        click=lambda rect: calls.append(rect),
        frame=lambda n: None,
        settle=lambda **kwargs: None,
    )
    result = {}
    with pytest.raises(AssertionError, match="did not satisfy tour await"):
        harness.advance_tour(driver, tour, result, SimpleNamespace(rows=[], input_values={}))
    assert "tour_steps" not in result
    assert result["tour_indices"] == [0]
    driver.click = lambda rect: tour.notify_used("confirm")
    harness.advance_tour(driver, tour, result, SimpleNamespace(rows=[], input_values={}))
    assert result["tour_indices"] == [0, 1]


def test_pre_satisfied_await_still_requires_a_fresh_real_target_interaction():
    """Prior inventory state must not replace exercising the guided example."""
    from chisurf.emtk.help_guide import EmTkGuidedTour

    tour = EmTkGuidedTour(
        [{"title": "Confirm", "target": "confirm", "await": True}, {"title": "Done"}],
        wait_for_controls=True,
    )
    tour.start()
    tour.notify_used("confirm")  # represents a real earlier interaction
    assert not tour.awaiting
    calls = []

    def click(rect):
        """Represent the fresh production handler, distinct from pre-satisfaction."""
        calls.append(rect)
        tour.notify_used("confirm")

    driver = SimpleNamespace(
        rect=lambda _: (1, 1, 10, 10),
        click=click,
        frame=lambda n: None,
        settle=lambda **kwargs: None,
    )
    result = {}
    harness.advance_tour(driver, tour, result, SimpleNamespace(rows=[], input_values={}))
    assert calls == [(1, 1, 10, 10)]
    assert result["tour_await_exercised"] is True


def test_overlapping_guide_targets_are_explicitly_ambiguous():
    """Identical labels and geometry in two contexts require an owner-specific target."""
    rows = [
        {"id": "Gain##gain", "visit_id": context, "rect": (10, 20, 40, 20)}
        for context in ("first-context", "second-context")
    ]
    with pytest.raises(AssertionError, match="ambiguous across contexts"):
        harness.resolved_tour_control(rows, "gain", (10, 20, 40, 20))


def test_native_dialog_guards_cancel_without_selecting_files():
    """A safe Help click must not block on a real modal event loop."""
    from contextlib import ExitStack

    from emtk.file_dialog import FileDialog

    result = {"dialogs_closed": 0, "blocked_actions": []}
    with ExitStack() as stack:
        harness._guards(stack, result)
        assert FileDialog().draw() is False
        import zmq

        socket = zmq.Context.instance().socket(zmq.REQ)
        with pytest.raises(RuntimeError, match="ZeroMQ"):
            socket.connect("tcp://127.0.0.1:8765")
        with pytest.raises(RuntimeError, match="ZeroMQ"):
            socket.bind("tcp://127.0.0.1:8775")
        with pytest.raises(RuntimeError, match="offline"):
            socket.send(b"must-not-reach-user-daemon")
        with pytest.raises(RuntimeError, match="offline"):
            socket.recv()
        socket.close(linger=0)
        with pytest.raises(RuntimeError, match="external process"):
            harness.subprocess.Popen(["must-not-run"])
        import os

        with pytest.raises(RuntimeError, match="external process"):
            os.system("must-not-run")
    assert result["dialogs_closed"] >= 1


def run_fixture(app, tmp_path, monkeypatch):
    """Exercise a real ImApp with the same native scenario as a manifest worker."""
    import chisurf.emtk.plugins

    monkeypatch.setattr(chisurf.emtk.plugins, "load_plugin", lambda *a, **k: app)
    monkeypatch.setattr(harness, "SIZE", (420, 320))
    monkeypatch.setenv("CHISURF_E2E_DIR", str(tmp_path))
    result = {
        "plugin": "fixture",
        "clicked": [],
        "skipped": [],
        "combos": [],
        "tabs": [],
        "dialogs_closed": 0,
        "errors": [],
    }
    harness._native("fixture", result, tmp_path / "fixture.png")
    return result


def test_offscreen_buttons_are_explicit_coverage_failure(tmp_path, monkeypatch):
    """A non-scrolling 140px window cannot prove delivery to all eighteen actions."""
    from emtk import im
    from emtk.app import ImApp

    from chisurf.emtk.help_guide import EmTkGuidedTour

    used = []

    def gui():
        """Submit overflow controls inside the real window clip."""
        im.begin("review-clip", (0, 0, 420, 140))
        for index in range(18):
            if im.button(f"Gain {index}"):
                used.append(index)
            im.set_item_tooltip("Exercise an in-memory action.")
        im.end()

    app = ImApp(gui)
    app.tour = EmTkGuidedTour([{"title": "Intro"}, {"title": "Next"}])
    with pytest.raises(AssertionError, match="coverage.*(visible|offscreen|reveal)"):
        run_fixture(app, tmp_path, monkeypatch)
    assert set(used) < set(range(18))


def test_collapsed_autoform_fold_reveals_and_exercises_hidden_action(tmp_path, monkeypatch):
    """AutoForm headers use direct button behavior and still belong in the inventory."""
    from emtk.app import ImApp
    from emtk.view_form import FormState, draw_form

    from chisurf.emtk.help_guide import EmTkGuidedTour

    used = []
    form = FormState()
    spec = {
        "sections": [
            {
                "type": "panel",
                "title": "Advanced",
                "description": "Advanced fields.",
                "collapsible": True,
                "collapsed": True,
                "sections": [
                    {
                        "type": "button_row",
                        "buttons": [
                            {
                                "action": "gain",
                                "label": "Gain",
                                "description": "An in-memory action.",
                            }
                        ],
                    }
                ],
            }
        ]
    }
    model = SimpleNamespace(gain=lambda: used.append("gain"))
    app = ImApp(lambda: draw_form(spec, model, form))
    app.form, app.spec = form, spec
    app.tour = EmTkGuidedTour(
        [{"title": "Intro"}, {"title": "Gain", "target": "gain", "await": True}],
        wait_for_controls=True,
    )
    form.on_used = app.tour.notify_used
    result = run_fixture(app, tmp_path, monkeypatch)
    assert used and "Gain##gain" in result["clicked"]
    assert any(row["kind"] == "autoform_fold" for row in result["controls"])
    assert result["tour_completed"] is True
    assert result["tour_await_exercised"] is True


def test_intro_tour_exercises_first_real_await_target(tmp_path, monkeypatch):
    """Advancing an introduction cannot stand in for interacting with the guided example."""
    from emtk import im
    from emtk.app import ImApp

    from chisurf.emtk.help_guide import EmTkGuidedTour

    used = []
    app = ImApp(lambda: None)

    def gui():
        """Notify the real tour only when the real button handler runs."""
        if im.button("Gain##gain"):
            used.append("gain")
            app.tour.notify_used("gain")
        im.set_item_tooltip("Perform the guided in-memory action.")
        app.remember("gain")

    app.gui = gui
    app.tour = EmTkGuidedTour(
        [{"title": "Intro"}, {"title": "Gain", "target": "gain", "await": True}, {"title": "Done"}],
        wait_for_controls=True,
    )
    result = run_fixture(app, tmp_path, monkeypatch)
    assert result.get("tour_await_target") == "gain"
    assert used == ["gain", "gain"]
    assert result["tour_indices"] == [0, 1, 2]
    assert result["tour_await_exercised"] is True


def test_scrollable_overflow_delivers_all_eighteen_real_callbacks(tmp_path, monkeypatch):
    """Actual wheel routing reveals clipped controls before their click is claimed."""
    from emtk import im
    from emtk.app import ImApp

    from chisurf.emtk.help_guide import EmTkGuidedTour

    used = []
    app = ImApp(lambda: None)

    def gui():
        """Draw a real scrollable child with more actions than fit."""
        im.begin("scrolling", (0, 0, 420, 320))
        im.begin_child((0, 0, 420, 140))
        for index in range(18):
            if im.button(f"Gain {index}##gain{index}"):
                used.append(index)
                app.tour.notify_used(f"gain{index}")
            im.set_item_tooltip("Exercise an in-memory action.")
            app.remember(f"gain{index}")
        im.end_child()
        im.end()

    app.gui = gui
    app.tour = EmTkGuidedTour(
        [{"title": "Intro"}, {"title": "Gain", "target": "gain0", "await": True}],
        wait_for_controls=True,
    )
    result = run_fixture(app, tmp_path, monkeypatch)
    assert set(used) == set(range(18))
    assert len(used) == 19  # all eighteen controls, then the real guided example
    assert len(result["clicked"]) == 18
    assert result["tour_completed"] is True


def test_worker_factory_failure_discards_stale_png(tmp_path, monkeypatch):
    """A previous screenshot must never make a failed factory look rendered."""
    monkeypatch.setenv("CHISURF_E2E_DIR", str(tmp_path))
    png = tmp_path / "example.png"
    png.write_bytes(b"previous run")
    monkeypatch.setattr(
        harness.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="factory failed"),
    )
    with pytest.raises(AssertionError):
        harness._isolated("example", "emtk")
    assert not png.exists()


@pytest.mark.parametrize("scale", [1, 2])
def test_translated_independent_contexts_deliver_same_named_buttons(tmp_path, monkeypatch, scale):
    """Painter transforms and independent context identity must preserve both Gain actions."""
    from emtk import im
    from emtk.app import ImApp
    from emtk.scaled_painter import ScaledPainter

    from chisurf.emtk.help_guide import EmTkGuidedTour

    used = []

    class Parent(ImApp):
        """Host two real local-coordinate child apps through the public draw_child API."""

        def __init__(self):
            super().__init__(self.render)
            self.boxes = [(10, 20, 80, 60), (110, 20, 80, 60)]
            self.children = [
                ImApp(lambda index=index: self.render_child(index)) for index in range(2)
            ]
            self.tour = EmTkGuidedTour(
                [{"title": "Intro"}, {"title": "Gain", "target": "gain", "await": True}],
                wait_for_controls=True,
            )
            self.child_focus = None

        def render_child(self, index):
            """The production-style real handler reports use to the parent tour."""
            if im.button("Gain##gain"):
                used.append(index)
                self.tour.notify_used("gain")
            im.set_item_tooltip("Run this child's in-memory action.")
            self.children[index].remember("gain")

        def draw(self, painter, x, y, w, h):
            """Keep the parent painter available for rendering hosted surfaces."""
            self.painter = painter
            super().draw(painter, x, y, w, h)

        def render(self):
            """Apply the real public painter adapters, without fake rectangle registration."""
            painter = ScaledPainter(self.painter, scale)
            for child, box in zip(self.children, self.boxes):
                self.draw_child(painter, child, *box, local_coordinates=True)
            x, y, _, _ = self.boxes[0]
            rx, ry, rw, rh = self.children[0]._item_rects["gain"]
            self.remember("gain", ((x + rx) * scale, (y + ry) * scale, rw * scale, rh * scale))

        def route(self, x, y):
            """Identify the child whose global rectangle contains this pointer."""
            for index, (bx, by, bw, bh) in enumerate(self.boxes):
                if bx <= x / scale < bx + bw and by <= y / scale < by + bh:
                    return index, x / scale - bx, y / scale - by
            return None, 0, 0

        def pointer_move(self, x, y, buttons=0, modifiers=0):
            """Forward host-global motion to the correct child-local surface."""
            super().pointer_move(x, y, buttons, modifiers)
            index, px, py = self.route(x, y)
            if index is not None:
                self.children[index].pointer_move(px, py, buttons, modifiers)

        def pointer_press(self, x, y, button, modifiers=0, clicks=1):
            """Forward an actual host press into a child context."""
            super().pointer_press(x, y, button, modifiers, clicks)
            index, px, py = self.route(x, y)
            self.child_focus = index
            if index is not None:
                self.children[index].pointer_press(px, py, button, modifiers, clicks)

        def pointer_release(self, x, y, button, modifiers=0):
            """Complete the actual press in the same child context."""
            super().pointer_release(x, y, button, modifiers)
            if self.child_focus is not None:
                bx, by, _, _ = self.boxes[self.child_focus]
                self.children[self.child_focus].pointer_release(
                    x / scale - bx, y / scale - by, button, modifiers
                )

    result = run_fixture(Parent(), tmp_path, monkeypatch)
    assert set(used[:2]) == {0, 1}
    assert used[-1] == 0, "the authoritative global guide target belongs to child zero"
    assert len(result["clicked"]) == 2
    assert len(set(result["clicked_ids"])) == 2


def test_action_entrypoints_are_not_windows():
    """Action-only manifests are classified as actions, not failed for lacking a window."""
    assert "menu_switch" in harness.IDS_ACTION
    assert "menu_switch" not in set(harness.IDS_EMTK)


def test_demo_choice_feeds_matching_file_and_folder_never_save(tmp_path):
    """A demo satisfies open/folder pickers; a save dialog is always cancelled."""
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.ptu").write_text("x")
    assert harness.demo_choice(tmp_path, "open", [("PTU", ["*.PTU"])]) == [str(tmp_path / "b.ptu")]
    assert harness.demo_choice(tmp_path, "folder", ()) == [str(tmp_path)]
    assert harness.demo_choice(tmp_path, "save", ()) == []
    assert harness.demo_choice(None, "open", ()) == []
    assert harness.demo_choice(tmp_path, "open", [("none", ["*.zzz"])]) == []


def test_tour_await_on_tagged_hardware_stays_refused():
    """The name-based exclusion is gone, but a declared hardware tag still blocks."""
    from chisurf.emtk.help_guide import EmTkGuidedTour

    tour = EmTkGuidedTour([{"title": "Go", "target": "go", "await": True}], wait_for_controls=True)
    tour.start()
    spec = {
        "sections": [{"type": "button_row", "buttons": [{"action": "go", "tags": ["hardware"]}]}]
    }
    driver = SimpleNamespace(rect=lambda _: (1, 1, 10, 10))
    with pytest.raises(AssertionError, match="unsafe control"):
        harness.advance_tour(driver, tour, {}, SimpleNamespace(rows=[], input_values={}), spec)


def test_a_held_job_ends_because_its_real_stop_was_pressed():
    """The gate holds a BackgroundJob open; only the press on the drawn Stop ends it, and no work is done."""
    import time

    from chisurf.emtk import job_gate
    from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

    ran, published = [], []
    job = BackgroundJob()
    job_gate.arm()
    job_gate.reset()
    try:
        assert job.start(lambda: ran.append(1) or 1, published.append, print)
        time.sleep(0.1)
        assert job.running and job_gate.active() == 1 and not ran, "the job was not held open"
        job.stop()  # what the drawn Stop button calls
        assert job_gate.wait_idle(5)
        job.poll()
        assert job_gate.stopped() == 1 and not ran and not published and not job.running
    finally:
        job_gate.disarm()
        job.close()


def test_a_released_job_runs_to_its_end_and_an_unarmed_gate_is_free():
    """Releasing lets the job compute and publish; without arming the gate nothing is admitted."""
    from chisurf.emtk import job_gate
    from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

    published = []
    job = BackgroundJob()
    try:
        job_gate.arm()
        assert job.start(lambda: 7, published.append, print)
        job_gate.release()
        assert job_gate.wait_idle(5)
        job.poll()
        assert published == [7]
        job_gate.disarm()
        assert job_gate.admit() is None
    finally:
        job_gate.disarm()
        job.close()
