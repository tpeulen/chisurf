"""The guided tours point at real controls and wait for the user.

Why a tour and not another demo
-------------------------------
The demos run themselves and show a finished result. That teaches what the
viewer can do and not one thing about *where the controls are* — which is the
part someone new is actually missing. A tour closes that gap by ringing one real
control at a time and waiting for the user to use it. It never presses anything
on their behalf: watching a button being pressed does not teach anyone where it
is.

What can silently go wrong, and is pinned here
----------------------------------------------
* a step waits for a command **that does not exist or is spelled wrong** — the
  tour then stops dead at that step with no error anywhere, which reads as the
  feature being broken. So every ``expect`` is checked against the command
  registry, and every tour is driven to completion through the real command
  layer;
* a step points at a control **that cannot be resolved** — the bubble is then
  centred and the tour silently becomes a slideshow. So the targets are resolved
  against a real chrome and required to land on something;
* the instruction and the awaited command **disagree** (the hint says one thing,
  ``expect`` waits for another). That is invisible until a user follows the hint
  and nothing happens, so the hint is required to contain the command;
* the bubble's rectangles **outlive the tour**, swallowing clicks on the chrome
  underneath.

The structures are chosen so the tours have right answers to check against:
EMD-3061 with PDB 5A63 is one experiment (human gamma-secretase at 3.4 A), and
1DG3/1F5N are one protein in two states.
"""
from __future__ import annotations

import json

import pytest

from chimol.tour import (
    TOUR_DIR,
    available_tours,
    load_tour,
)

TOURS = [name for name, _title in available_tours()]

#: The commands each tour drives, in order — what a user following the hints
#: would type. Kept here rather than derived from ``expect`` so the test is a
#: second opinion: a tour whose ``expect`` drifted from its instructions fails.
WALKTHROUGH = {
    "superpose": [
        "fetch 1DG3",
        "fetch 1F5N",
        "color skyblue, 1dg3",
        "align 1f5n, 1dg3",
        "super 1f5n, 1dg3",
        "rms 1f5n, 1dg3",
        "zoom 1f5n",
    ],
    "fit_in_map": [
        "fetch EMD-3061",
        "map_info",
        "isosurface dens, EMD-3061",
        "volume_level EMD-3061, 0.06",
        "hide_dust EMD-3061, 30",
        "fetch 5A63",
        "translate [6, -4, 3], 5a63",
        "fitmap 5a63, EMD-3061, 3.4",
        "molmap 5a63, 3.4, sim",
    ],
    # The pick is a *typed* one -- `wizard pick, 920` is the same path a click
    # takes (see the wizard's hook), and 920 is 148l's residue 119 CB: fixed
    # test data, so the index is stable.
    "labelling": [
        "load 148l.pdb",
        "wizard labelling",
        "wizard pick, 920",
        "wizard dye, Cy5",
        "wizard apply",
        "wizard done",
    ],
}


def test_there_are_tours():
    """The premise."""
    assert TOURS, f"no tours in {TOUR_DIR}"


@pytest.mark.parametrize("name", TOURS)
def test_a_tour_reads_and_has_an_opening_step(name):
    """Every tour opens by saying what it is for, before asking for anything."""
    tour = load_tour(name)
    assert tour.steps
    first = tour.steps[0]
    assert not first.waits, "the opening step must not wait for a command"
    assert first.text, "the opening step must say what the tour is for"


@pytest.mark.parametrize("name", TOURS)
def test_the_step_count_in_the_text_is_right(name):
    """Trivial to get wrong, and the first thing a reader checks.

    The opening step tells the user how long this will take. Written by hand it
    forgets to count itself, which is exactly what happened the first time.
    """
    words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    }
    tour = load_tour(name)
    claimed = [
        value for word, value in words.items()
        if f"{word} steps" in tour.steps[0].text.lower()
    ]
    assert claimed, f"the opening step of {name} does not say how many steps"
    assert claimed[0] == len(tour.steps), (
        f"{name} says {claimed[0]} steps and has {len(tour.steps)}"
    )


@pytest.mark.parametrize("name", TOURS)
def test_every_waiting_step_says_what_to_do(name):
    """A step that waits in silence is a tour that has stopped working."""
    for index, step in enumerate(load_tour(name).steps):
        if step.waits:
            assert step.hint, f"{name} step {index + 1} waits with no hint"
            head = step.expect.split()[0]
            assert head in step.hint, (
                f"{name} step {index + 1} waits for {step.expect!r} but its "
                f"hint does not mention {head!r}: {step.hint!r}"
            )


@pytest.mark.parametrize("name", TOURS)
def test_every_awaited_command_exists(name):
    """A typo in ``expect`` stops the tour dead with nothing raised anywhere."""
    from toolkit_free import probe

    heads = sorted({
        step.expect.split()[0].lower()
        for step in load_tour(name).steps if step.waits
    })
    measured = probe(f'''
        app = open_app(size=(400, 300))
        for head in {heads!r}:
            emit(head, "yes" if app.cmd._registry.resolve(head) else "no")
    ''')
    for head in heads:
        assert measured[head] == "yes", (
            f"{name} waits for '{head}', which is not a command"
        )


@pytest.mark.parametrize("name", TOURS)
def test_no_step_carries_unrendered_markup(name):
    """The tours are written in the widget tours' dialect; this chrome paints
    one font, so the tags are stripped rather than shown."""
    tour = load_tour(name)
    for step in tour.steps:
        assert "<" not in step.text and ">" not in step.text
        assert "<" not in step.hint and ">" not in step.hint


def test_a_tour_advances_only_on_its_own_step():
    """Running a later step's command early must not skip ahead.

    A tour that jumped forward on any recognised command would report a
    workflow the user never performed.
    """
    tour = load_tour("superpose")
    tour.advance()  # past the opening step
    at = tour.index
    assert not tour.observe("rms 1f5n, 1dg3"), "a later command advanced the tour"
    assert tour.index == at
    assert tour.observe("fetch 1DG3")
    assert tour.index == at + 1


def test_extra_arguments_still_satisfy_a_step():
    """``expect`` matches the leading words, deliberately.

    A user who adds a contour level of their own to the command the tour asked
    for has done the step, not deviated from it.
    """
    tour = load_tour("fit_in_map")
    while tour.current is not None and not tour.current.waits:
        tour.advance()
    step = tour.current
    assert step.satisfied_by(step.expect + ", 0.03")
    assert not step.satisfied_by("zoom all")


@pytest.mark.parametrize("name", TOURS)
def test_the_tour_walks_to_the_end_through_real_commands(name):
    """The whole thing, driven the way a user would drive it.

    This is the test that would have caught the real defect found while writing
    these: the map tour said ``hide_dust dens, 30``, naming the *contour object*
    where the command wants the **map**. The command errored, the step never
    completed, and the tour simply stopped -- with the instruction on screen
    still saying to do the thing that does not work.
    """
    from toolkit_free import probe

    steps = WALKTHROUGH[name]
    lines = "\n".join(f'        run({command!r})' for command in steps)
    measured = probe(f'''
        app = open_app(size=(1000, 700))
        errors = []
        app.cmd.set_error_callback(errors.append)
        gui = app.renderer._internal_gui

        app.cmd.do("tour {name}")
        emit("started", "yes" if gui.tour is not None else "no")
        gui.advance_tour()   # past the opening step

        def run(command):
            before = gui.tour.index if gui.tour else -1
            errors.clear()
            app.cmd.do(command)
            after = gui.tour.index if gui.tour else "done"
            emit(command, f"{{before}}->{{after}}")
            emit("errors:" + command, "; ".join(errors) or "none")
            # The ring has to land on a real control, or the bubble is a
            # slideshow floating in the middle of the viewport.
            if gui.tour is not None and gui.tour.current is not None:
                rect = gui.tour_target_rect(gui.tour.current.target)
                emit("target:" + command,
                     "yes" if (rect.w > 0 and rect.h > 0) else "no")
            app.renderer.draw_frame()

{lines}

        emit("finished", "yes" if gui.tour is None else "no")
        # The bubble's rectangles must not outlive it: they are hit-tested, and
        # one left behind swallows clicks on the chrome underneath.
        emit("rects_cleared",
             "yes" if gui._tour_rect.w == 0 and gui._tour_close_rect.w == 0 else "no")
    ''')

    assert measured["started"] == "yes"
    for command in steps:
        assert measured[f"errors:{command}"] == "none", (
            f"{name}: '{command}' errored: {measured[f'errors:{command}']}"
        )
    moved = [measured[command] for command in steps]
    assert measured["finished"] == "yes", (
        f"{name} did not reach the end; steps went {moved}"
    )
    assert measured["rects_cleared"] == "yes"


@pytest.mark.parametrize("name", TOURS)
def test_the_tour_walks_by_pressing_run(name):
    """The whole tour, driven the way most people will drive it.

    `Run` issues the step's command rather than skipping it, so this walks the
    workflow end to end -- and it is the path a user takes when they would
    rather click than type. Three things are asserted at every step, and each
    was broken when this was written:

    * **no command errors.** `Run` used to issue `expect`, which is a *prefix*
      for matching: a step matching any `translate` answered "missing required
      argument" when pressed. A step whose expect is a prefix now carries the
      command to run;
    * **the ring lands on something.** A step that points at a window nobody
      opened rings nothing and describes something that is not on screen --
      reported as "some menus/windows do not seem to appear". A step's `setup`
      opens its subject when the step is shown;
    * **it reaches the end.** A step that neither advances nor errors is a
      tour that has stopped, silently.
    """
    from toolkit_free import probe

    measured = probe(f'''
        app = open_app(size=(1100, 700))
        gui = app.renderer._internal_gui
        errors = []
        app.cmd.set_error_callback(errors.append)

        app.cmd.do("tour {name}")
        emit("started", "yes" if gui.tour is not None else "no")

        problems, missing, walked = [], [], 0
        for _ in range(40):
            if gui.tour is None:
                break
            step = gui.tour.current
            if step is None:
                break
            walked += 1
            app.renderer.draw_frame()
            rect = gui.tour_target_rect(step.target)
            if step.target and not (rect.w > 0 and rect.h > 0):
                missing.append(step.title)
            errors.clear()
            before = gui.tour.index
            gui.advance_tour()
            if errors:
                problems.append(step.title + ": " + errors[0])
            after = gui.tour.index if gui.tour is not None else -1
            if after == before:
                problems.append(step.title + ": the tour did not move on")
                break

        emit("walked", walked)
        emit("finished", "yes" if gui.tour is None else "no")
        emit("errors", " | ".join(problems) or "none")
        emit("missing", " | ".join(missing) or "none")
    ''')

    assert measured["started"] == "yes"
    assert measured["errors"] == "none", measured["errors"]
    assert measured["missing"] == "none", (
        f"these steps point at nothing: {measured['missing']}"
    )
    assert measured["finished"] == "yes", (
        f"the tour stopped after {measured['walked']} steps"
    )
    assert int(measured["walked"]) == len(load_tour(name).steps)


@pytest.mark.parametrize("name", TOURS)
def test_what_run_issues_is_a_command(name):
    """Every step has something to run, and it names a real command.

    Deliberately *not* "does it look complete": `map_info` takes no arguments
    and is a whole command, while `translate` on its own is a prefix that fails
    when issued. Whether a command is complete is a question only running it
    can answer, which is what the walk above does -- this checks the cheaper
    property, that the verb exists at all, so a typo is named here rather than
    surfacing as a failed step.
    """
    from toolkit_free import probe

    verbs = sorted({
        step.command.split()[0].lower()
        for step in load_tour(name).steps
        if step.waits and step.command.strip()
    })
    assert verbs, f"{name} has no runnable step"
    measured = probe(f'''
        app = open_app(size=(400, 300))
        for verb in {verbs!r}:
            emit(verb, "yes" if app.cmd._registry.resolve(verb) else "no")
    ''')
    for verb in verbs:
        assert measured[verb] == "yes", f"{name} would run {verb!r}, which is not a command"


@pytest.mark.parametrize("name", TOURS)
def test_every_target_is_a_control_the_chrome_knows(name):
    """A target spelled wrong resolves to nothing and centres the bubble."""
    known = {"menu", "toolbar", "command", "wizard", "object", "movie", "sequence", "window"}
    for index, step in enumerate(load_tour(name).steps):
        for key in step.target:
            assert key in known, (
                f"{name} step {index + 1} points at '{key}', which "
                f"tour_target_rect does not understand"
            )


def test_the_tours_are_on_the_help_menu():
    """Shipped and unreachable is the failure the generated menu exists to avoid.

    Under **Help**, not Demo. A demo runs itself and shows a finished result; a
    tour points at real controls and waits for you to press them, which is what
    someone opens the command list for.
    """
    from chimol.app.menu_bar import DEMO_MENU, HELP_MENU

    def commands_of(entries):
        found = set()
        for entry in entries or ():
            command = getattr(entry, "command", None)
            if command:
                found.add(str(command))
            found |= commands_of(getattr(entry, "children", None))
        return found

    # In a submenu, not loose in Help: more tours are coming, and loose they
    # would push Reset GUI and Debug Mode off the bottom -- which are what Help
    # is opened for when something has gone wrong.
    under_help = commands_of(HELP_MENU)
    top_level = {str(getattr(e, "command", "") or "") for e in HELP_MENU}
    for name in TOURS:
        assert f"tour {name}" in under_help, f"{name} is not under Help"
        assert f"tour {name}" not in top_level, f"{name} is a loose Help row"
        assert f"tour {name}" not in commands_of(DEMO_MENU), (
            f"{name} is still on the Demo menu"
        )


@pytest.mark.parametrize("name", TOURS)
def test_the_shipped_file_is_valid_json_with_a_comment(name):
    """The ``_comment`` says who reads the file; the tours are read by hand too."""
    data = json.loads((TOUR_DIR / f"{name}.json").read_text(encoding="utf-8"))
    assert data.get("title")
    assert data.get("_comment"), "say what this file is and what reads it"
