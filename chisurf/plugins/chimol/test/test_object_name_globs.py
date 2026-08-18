"""`hide av_*`: a name with a wildcard in it names objects, everywhere.

`delete av_*` and `order av_*` took patterns; `disable`, `hide` and a selection
did not -- so with thirty-five objects on screen from a labelling network, the
obvious way to put the dye clouds away answered "Unsupported representation for
show/hide: av_*", and the PyMOL spelling answered `Invalid selection name
"av_*"`. One resolver, used wherever objects are named, is the fix; these are
the four spellings somebody actually types.

The `hide` case has an ordering to it that is worth stating: the word is read
as *objects* before it is read as a selection, because a dye cloud has no atoms
-- reading `hide av_*` as "hide everything in the atoms those objects cover"
hides nothing at all, which is the more surprising of two defensible readings.
"""
from __future__ import annotations

import pytest

from chimol.commands.command import Cmd
from chimol.testing.mock_viewer import MockViewer, MockWindow


def _scene(names) -> Cmd:
    viewer = MockViewer()
    viewer.objects.clear()
    for index, name in enumerate(names):
        viewer._add_mock_object(f"obj{index}", name)
    return Cmd(MockWindow(viewer))


NAMES = ["t4l", "av_119A_mp", "av_44D_mp", "av_86A_mp", "sele_helper"]


def _visible(cmd) -> set:
    return {
        entry.name for entry in cmd.window.viewer.objects.values()
        if getattr(entry, "visible", True)
    }


@pytest.mark.parametrize("line", ["hide av_*", "disable av_*"])
def test_a_pattern_hides_the_objects_it_names(line):
    cmd = _scene(NAMES)
    said: list[str] = []
    cmd.set_error_callback(said.append)
    cmd.do(line)
    assert not said, said
    assert _visible(cmd) == {"t4l", "sele_helper"}


def test_and_shows_them_again():
    cmd = _scene(NAMES)
    cmd.do("hide av_*")
    cmd.do("enable av_*")
    assert _visible(cmd) == set(NAMES)


def test_a_pattern_that_matches_nothing_is_not_silent():
    cmd = _scene(NAMES)
    said: list[str] = []
    cmd.set_error_callback(said.append)
    cmd.do("disable nothing_*")
    assert said, "a pattern that matched nothing said nothing"


REAL = '''
app = open_app(size=(600, 400))
cmd, viewer = app.cmd, app.viewer
cmd.do("load 148l.pdb")
cmd.do("create cartoon, 148l")          # an object named after a representation
cmd.do("create av_one, 148l")
cmd.do("create av_two, 148l")

def visible():
    return ",".join(sorted(e.name for e in viewer.objects.values() if e.visible))

emit("all", visible())
cmd.do("hide av_*")
emit("after_hide_pattern", visible())
cmd.do("enable av_*")
emit("after_enable_pattern", visible())
cmd.do("hide cartoon")                  # a representation, not the object
emit("after_hide_representation", visible())
cmd.do("disable 148l")
emit("after_disable_name", visible())

# The PyMOL spelling: a wildcard where a selection goes.
said = []
cmd.set_message_callback(said.append)
cmd.do("count_atoms av_*")
emit("count_glob", said[-1] if said else "nothing")
said.clear()
cmd.do("count_atoms 148l")
emit("count_one", said[-1] if said else "nothing")
'''


@pytest.fixture(scope="module")
def real():
    from toolkit_free import probe

    return probe(REAL, timeout=600)


def test_a_pattern_hides_only_what_it_matches_on_a_real_viewer(real):
    assert set(real["all"].split(",")) == {"148l", "cartoon", "av_one", "av_two"}
    assert set(real["after_hide_pattern"].split(",")) == {"148l", "cartoon"}
    assert set(real["after_enable_pattern"].split(",")) == set(real["all"].split(","))


def test_a_representation_is_still_a_representation(real):
    """`hide cartoon` must not start looking for an object called cartoon."""
    assert set(real["after_hide_representation"].split(",")) == set(real["all"].split(",")), (
        "hiding a representation hid an object that happens to share its name"
    )


def test_a_plain_object_name_still_works(real):
    assert "148l" not in real["after_disable_name"].split(",")


def test_a_wildcard_selection_resolves_to_the_objects_it_matches(real):
    """`hide everything, av_*` -- the PyMOL spelling of the same thing.

    Counted rather than masked: two copies of one structure, so the glob's
    answer is exactly twice the single object's.
    """
    import re

    def count(line):
        digits = re.findall(r"\d+", line.replace(",", ""))
        assert digits, line
        return int(digits[0])

    assert count(real["count_glob"]) == 2 * count(real["count_one"])


def test_an_unknown_plain_name_is_still_an_error():
    """A typo is not a pattern: `hide av_119` should not quietly match nothing."""
    from chimol.core.selection.parser import Evaluator, UnknownSelectionName

    cmd = _scene(NAMES)
    viewer = cmd.window.viewer
    evaluator = Evaluator(viewer)
    object_id = next(iter(viewer.objects))
    with pytest.raises(UnknownSelectionName):
        evaluator.evaluate("av_119", object_id=object_id)
