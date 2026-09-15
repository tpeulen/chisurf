"""A change rebuilds what changed, and the cached geometry is the right geometry.

The scene was rebuilt *whole* whenever anything happened. Measured on seven
copies of one structure: colouring one object cost 805 ms and rebuilt all seven
cartoons and all seven ambient-occlusion neighbour searches; an
``update_view()`` that changed nothing cost 541 ms and rebuilt all seven. The
only invalidation available was one generation counter for the entire viewer,
which cannot say *which* object changed -- the same shape of fault as the
chrome's single fingerprint, one layer down.

Each object now carries a fingerprint of what its geometry was built from
(:func:`chimol.core.model.object_state.build_fingerprint`), compared before a
build and stored after one, so state the build itself derives costs nothing.

Two things have to hold, and the second is the one that matters:

* a change rebuilds the objects it touches and no more;
* what a cache hit hands back is what a rebuild would have produced -- checked
  by forcing a rebuild and comparing the geometry, after every kind of change
  the viewer offers. A fingerprint that misses a field shows stale geometry,
  which is worse than being slow.
"""
from __future__ import annotations

import pytest

from toolkit_free import probe

SCRIPT = '''
import hashlib

app = open_app(size=(700, 500))
cmd, viewer = app.cmd, app.viewer
cmd.do("load 148l.pdb")
for index in range(3):
    cmd.do("create copy_%d, 148l" % index)
app.renderer._draw()
viewer.update_view(); viewer.update_view()          # settle derived state

import chimol.core.viewer.scene as scene_module
built = {"n": 0}
_original = scene_module.SceneMixin._build_scene_for_current_object
def counting(self, object_prefix=None):
    built["n"] += 1
    return _original(self, object_prefix=object_prefix)
scene_module.SceneMixin._build_scene_for_current_object = counting

def summary():
    """Everything drawn, described so a difference cannot hide."""
    scene = viewer._scene
    out = []
    for obj in (getattr(scene, "objects", None) or ()):
        geometry = obj.geometry
        digest = hashlib.sha1()
        for name in ("positions", "colors", "indices", "radii"):
            value = getattr(geometry, name, None)
            if value is not None:
                digest.update(np.ascontiguousarray(value).tobytes())
        out.append((str(obj.id), str(geometry.kind), digest.hexdigest()[:12]))
    return out

def forced():
    """The same scene, with every cache thrown away."""
    for entry in viewer.objects.values():
        entry.built_fingerprint = None
        entry.built_scene_objects = None
    viewer.update_view()
    return summary()

def rebuilt(action):
    built["n"] = 0
    action()
    return built["n"]

actions = [
    ("nothing", lambda: viewer.update_view()),
    ("colour one", lambda: cmd.do("color red, copy_0")),
    ("colour all", lambda: cmd.do("color yellow")),
    ("spectrum", lambda: cmd.do("spectrum count, rainbow, copy_1")),
    ("show sticks", lambda: cmd.do("show sticks, copy_1")),
    ("hide cartoon", lambda: cmd.do("hide cartoon, copy_1")),
    ("show spheres", lambda: cmd.do("show spheres, copy_2")),
    ("label", lambda: cmd.do("label copy_2 and resi 5, 'x'")),
    ("unlabel", lambda: cmd.do("label copy_2, ''")),
    ("bond", lambda: cmd.do("bond copy_0 and resi 5 and name CA, copy_0 and resi 6 and name CA")),
    ("select", lambda: cmd.do("select sele, resi 10-20")),
    ("deselect", lambda: cmd.do("deselect")),
    ("hide one", lambda: cmd.do("disable copy_2")),
    ("show one", lambda: cmd.do("enable copy_2")),
    ("a setting", lambda: cmd.do("set stick_radius, 0.31")),
    ("another setting", lambda: cmd.do("set cartoon_transparency, 0.2")),
    ("delete one", lambda: cmd.do("delete copy_0")),
]

for name, action in actions:
    count = rebuilt(action)
    viewer.update_view()
    cached = summary()
    emit("rebuilt:" + name, count)
    emit("honest:" + name, "yes" if cached == forced() else "no")

emit("objects", len(viewer.objects))

# A *read* must not dirty anything. The sequence strip asks every object for
# its per-residue colours on every repaint, and asking used to recompute and
# assign them -- so drawing the panel left every object permanently dirty.
from chimol.core.model.object_state import build_fingerprint
viewer.update_view()
before = {oid: build_fingerprint(e) for oid, e in viewer.objects.items()}
for object_id in list(viewer.objects):
    viewer.get_residue_colors(object_id)
    viewer.get_residue_colors(object_id)
after = {oid: build_fingerprint(e) for oid, e in viewer.objects.items()}
emit("reads_dirty", ",".join(sorted(k for k in before if before[k] != after[k])) or "none")
emit("read_rebuilds", rebuilt(lambda: viewer.update_view()))
# ...and the colours are still right after a colour command.
def id_of(name):
    return next(oid for oid, e in viewer.objects.items() if e.name == name)

before_colour = viewer.get_residue_colors(id_of("copy_1"))
cmd.do("color green, copy_1")
after_colour = viewer.get_residue_colors(id_of("copy_1"))
emit("colour_seen", "no" if before_colour is None or after_colour is None
     else ("yes" if not np.allclose(before_colour, after_colour) else "no"))
emit("colour_value", ",".join("%.2f" % v for v in np.asarray(after_colour)[0]))

# `show <rep>, <one object>` is one object's business.
viewer.update_view()
emit("show_one_rebuilds", rebuilt(lambda: cmd.do("show spheres, copy_1")))

# Labelling turns the labels on for the object named, not for whichever object
# happened to be active when the command ran.
def labelled_objects():
    return {e.name for e in viewer.objects.values()
            if getattr(e.state, "show_labels", False)}

was = labelled_objects()
viewer.activate_object(id_of("copy_1")).__enter__()   # a different active object
cmd.do("label copy_2 and resi 7, 'y'")
turned_on = labelled_objects() - was
emit("labels_turned_on", ",".join(sorted(turned_on)) or "none")
emit("labels_elsewhere", ",".join(sorted(turned_on - {"copy_2"})) or "none")

# The steady state: with nothing happening, nothing is rebuilt.
viewer.update_view()
emit("idle_rebuilds", rebuilt(lambda: viewer.update_view()))
# ...and one object's colour rebuilds one object.
emit("colour_one_rebuilds", rebuilt(lambda: cmd.do("color blue, copy_1")))
# ...while a global setting rebuilds every one of them.
emit("setting_rebuilds", rebuilt(lambda: cmd.do("set stick_radius, 0.44")))
emit("visible", sum(1 for e in viewer.objects.values() if e.visible))
'''


@pytest.fixture(scope="module")
def swept():
    return probe("import numpy as np\n" + SCRIPT, timeout=900)


INTERACTIONS = [
    "nothing", "colour one", "colour all", "spectrum", "show sticks",
    "hide cartoon", "show spheres", "label", "unlabel", "bond", "select",
    "deselect", "hide one", "show one", "a setting", "another setting",
    "delete one",
]


@pytest.mark.parametrize("interaction", INTERACTIONS)
def test_the_cached_geometry_is_the_geometry(swept, interaction):
    """After every change, what the cache serves equals a forced rebuild."""
    assert swept.get("honest:" + interaction) == "yes", (
        f"stale geometry after: {interaction}"
    )


def test_nothing_changed_means_nothing_is_rebuilt(swept):
    """`update_view` used to rebuild every object in the scene, every time."""
    assert int(swept["idle_rebuilds"]) == 0


def test_one_objects_colour_rebuilds_one_object(swept):
    assert int(swept["colour_one_rebuilds"]) == 1


def test_asking_an_object_for_its_colours_does_not_dirty_it(swept):
    """A read that writes is a cache that never hits.

    ``get_residue_colors`` recomputed the per-residue colours and *assigned*
    them, on every branch. The sequence strip asks for them once per object on
    every repaint -- so every object was dirty again the instant the panel was
    drawn, and colouring one object of seven rebuilt six of them. Keyed on its
    inputs now, so the second call recomputes nothing.
    """
    assert swept["reads_dirty"] == "none", (
        f"reading the colours dirtied: {swept['reads_dirty']}"
    )
    assert int(swept["read_rebuilds"]) == 0


def test_the_colours_are_still_right_after_the_cache_hits(swept):
    """The other half: a keyed recompute that misses a colour command."""
    assert swept["colour_seen"] == "yes", (
        f"the cache served the old colours: {swept['colour_value']}"
    )


def test_showing_a_representation_on_one_object_rebuilds_one_object(swept):
    assert int(swept["show_one_rebuilds"]) == 1


def test_labelling_turns_the_labels_on_for_the_object_it_labelled(swept):
    """`show_labels` is per-object, and was written outside any activation.

    So `label copy_3 and resi 7` switched labels on for whichever object was
    active -- a wrong picture, not merely a slow one.
    """
    assert swept["labels_turned_on"] in ("copy_2", "none"), swept["labels_turned_on"]
    assert swept["labels_elsewhere"] == "none", (
        f"labelling copy_2 turned the labels on for: {swept['labels_elsewhere']}"
    )


def test_a_global_setting_rebuilds_everything(swept):
    """Stick radius, cartoon quality, occlusion: every builder reads them."""
    assert int(swept["setting_rebuilds"]) == int(swept["visible"])
