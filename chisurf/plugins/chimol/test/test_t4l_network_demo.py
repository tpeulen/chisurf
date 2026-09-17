"""The T4L demo: a whole published labelling network, end to end.

`demo labelling` shows what an accessible volume is, on two positions. This is
what those clouds are *for*: seventeen labelling positions on T4 lysozyme --
donor and acceptor variants of twelve sites -- and ninety-nine measured
inter-dye distances, shipped as the fps.json they were distributed as
(`t4l_network.fps.json`) with the structure they were measured against
(`t4l_3gun.pdb`, PDB 3GUN).

The demo is the assertion here. It computes every position's accessible volume
from the definition the document carries, marks each cloud's density-weighted
mean with the position's name, draws the document's distances between the
means, and opens the circular view on one of the document's seven distance
sets. What this file checks is that the whole of that survives -- the data
shipping intact, the structure carrying every attachment atom, and the demo
producing the objects, labels, lines and network it describes.
"""

from __future__ import annotations

import json
import pathlib

import chimol
import pytest
from toolkit_free import probe

DEMOS = pathlib.Path(chimol.__file__).resolve().parent / "data" / "demos"
PLAN = DEMOS / "t4l_network.fps.json"
STRUCTURE = DEMOS / "t4l_3gun.pdb"


@pytest.fixture(scope="module")
def document() -> dict:
    if not PLAN.is_file():
        pytest.skip(f"missing {PLAN}")
    return json.loads(PLAN.read_text())


# --------------------------------------------------------------------------- #
# What ships
# --------------------------------------------------------------------------- #
def test_the_network_is_the_whole_network(document):
    assert len(document["Positions"]) == 17
    assert len(document["Distances"]) == 99
    assert len(document["χ²"]) == 7, "the conformer score sets are the datasets"


def test_every_distance_names_two_positions_that_exist(document):
    names = set(document["Positions"])
    for key, fields in document["Distances"].items():
        assert fields["position1_name"] in names, key
        assert fields["position2_name"] in names, key
        assert float(fields["Forster_radius"]) > 0.0, key


def test_every_score_set_names_distances_that_exist(document):
    declared = set(document["Distances"])
    for name, body in document["χ²"].items():
        assert body["distances"], name
        assert set(body["distances"]) <= declared, name


def test_the_document_says_where_it_came_from(document):
    """Shipped data with no provenance is data nobody can check."""
    origin = document.get("Provenance") or {}
    assert "3GUN" in str(origin.get("structure", ""))
    assert "IMP.bff" in str(origin.get("source", ""))
    assert origin.get("changed_for_this_copy"), (
        "the copy differs from its source and does not say how"
    )


def test_the_structure_carries_every_attachment_atom(document):
    if not STRUCTURE.is_file():
        pytest.skip(f"missing {STRUCTURE}")
    atoms = [
        line for line in STRUCTURE.read_text().splitlines() if line.startswith(("ATOM  ", "HETATM"))
    ]
    for name, fields in document["Positions"].items():
        residue = int(fields["residue_seq_number"])
        wanted = str(fields["atom_name"]).strip()
        chain = str(fields["chain_identifier"]).strip()
        assert any(
            line[21] == chain and int(line[22:26]) == residue and line[12:16].strip() == wanted
            for line in atoms
        ), f"{name}: no {wanted} on residue {residue} of chain {chain}"


# --------------------------------------------------------------------------- #
# What the demo builds
# --------------------------------------------------------------------------- #
SCRIPT = """
app = open_app(size=(900, 600))
cmd, gui, viewer = app.cmd, app.viewer.gui, app.viewer
errors = []
cmd.set_error_callback(errors.append)
cmd.do("demo t4l_network")
app.renderer._draw()
emit("errors", "|".join(errors) or "none")

avs = [oid for oid, e in viewer.objects.items()
       if getattr(e.state, "av", None) is not None]
means = [oid for oid, e in viewer.objects.items()
         if getattr(e.state, "av_mean_object_id", None) is None
         and getattr(e.state, "labels", None)]
emit("av_objects", len(avs))
emit("labelled_means", len(means))
emit("labels", ",".join(sorted(
    str(t) for e in viewer.objects.values()
    for t in (getattr(e.state, "labels", None) or {}).values()))[:120])

lines = viewer.measurements
emit("lines_total", len(lines))
emit("lines_visible", sum(1 for f in lines.values() if f.get("visible", True)))

panel = gui.panels.get("fps_circle")
emit("panel", type(panel).__name__ if panel else "none")
emit("dataset", panel.dataset)
emit("datasets", len(panel.datasets()))
circle = panel.build(0, 0, 400, 400)
emit("sectors", ",".join(s.name for s in circle.sectors))
emit("dots", len(circle._points))
emit("chords", len(circle._links))

# Hovering a position lights it and its own distances -- in the scene.
name = sorted(panel._dots)[0]
x, y = panel._dots[name]
class R:
    x = y = 0.0
    w = h = 1000.0
panel.hover(x, y, R())
emit("hovered", str(panel.hovered))
emit("lit", sum(1 for f in viewer.measurements.values()
                if tuple(f.get("color", ())) == (0.25, 1.0, 0.92, 1.0)))
panel.hover(-999.0, -999.0, R())
emit("lit_after_leaving", sum(1 for f in viewer.measurements.values()
                              if tuple(f.get("color", ())) == (0.25, 1.0, 0.92, 1.0)))
"""


@pytest.fixture(scope="module")
def ran():
    return probe(SCRIPT, timeout=900)


def test_the_demo_runs_clean(ran):
    assert ran["errors"] == "none"


def test_it_computes_every_positions_accessible_volume(ran):
    assert int(ran["av_objects"]) == 17


def test_every_mean_position_carries_its_positions_name(ran):
    """A scene of dye clouds is a scene of anonymous blobs without them."""
    assert int(ran["labelled_means"]) == 17
    assert "119A" in ran["labels"] or "5D" in ran["labels"]


def test_it_draws_the_documents_distances(ran):
    # 99 from the document, plus the four hand-drawn edges the demo shows first.
    assert int(ran["lines_total"]) == 103
    # ...of which the chosen dataset's 20, plus those four, are on screen.
    assert int(ran["lines_visible"]) == 24


def test_it_opens_the_network_on_one_dataset(ran):
    assert ran["panel"] == "FpsCirclePanel"
    assert ran["dataset"].startswith("chi2_C1_20p")
    assert int(ran["datasets"]) == 8  # every distance, then seven sets
    assert ran["sectors"] == "A"
    assert int(ran["dots"]) == 17
    assert int(ran["chords"]) == 20


def test_hovering_a_position_lights_its_distances_and_then_lets_go(ran):
    assert ran["hovered"] != "None"
    assert int(ran["lit"]) > 0, "hovering a position lit nothing in the scene"
    assert int(ran["lit_after_leaving"]) == 0, "the highlight outlived the hover"


# --------------------------------------------------------------------------- #
# What the demo *looks* like
# --------------------------------------------------------------------------- #
LOOK = """
app = open_app(size=(900, 600))
cmd, gui, viewer = app.cmd, app.viewer.gui, app.viewer
cmd.do("demo t4l_network")
app.renderer._draw()

groups = [row.name for row in gui.rows if getattr(row, "is_group", False)]
emit("groups", ",".join(sorted(groups)))
emit("rows", len(gui.rows))
emit("closed", ",".join(sorted(
    row.name for row in gui.rows
    if getattr(row, "is_group", False) and not row.group_open
)))
clouds = [e for e in viewer.objects.values() if getattr(e.state, "av", None) is not None]
emit("clouds", len(clouds))
emit("clouds_visible", sum(1 for e in clouds if e.visible))
styles = {str((e.state.volume_levels or [{}])[0].get("style", "")) for e in clouds}
emit("cloud_style", ",".join(sorted(styles)))
alphas = {round(float((e.state.av_color or (0, 0, 0, 1))[3]), 2) for e in clouds}
emit("cloud_alpha", ",".join(str(a) for a in sorted(alphas)))
"""


@pytest.fixture(scope="module")
def look():
    return probe(LOOK, timeout=900)


def test_the_clouds_and_the_means_are_two_rows_not_thirty_four(look):
    """A network's clouds are wanted or not wanted as a set."""
    assert set(look["groups"].split(",")) == {"av_clouds", "av_means"}
    assert set(look["closed"].split(",")) == {"av_clouds", "av_means"}
    assert int(look["rows"]) < 120, "the object list is still one row per object"


def test_a_network_of_clouds_is_drawn_as_wireframe(look):
    """Seventeen solid contours are a fog with a structure somewhere in it."""
    assert int(look["clouds"]) == 17
    assert look["cloud_style"] == "mesh"
    assert float(look["cloud_alpha"]) > 0.3, "a wireframe faded like a surface disappears"


def test_the_demo_starts_with_the_structure_visible(look):
    """The clouds are there, switched off, one click from being back."""
    assert int(look["clouds_visible"]) == 0


def test_the_script_does_not_name_what_the_loader_invents():
    """A demo is *data* shipped beside code, and the two can be out of step.

    The script switched off a group `fps_load` had created -- and a session
    running the new script against older code answered "unknown object
    av_clouds", because the group did not exist yet. Whoever makes the objects
    decides how they are first shown; the script says what the demo is about.
    """
    script = (DEMOS / "t4l_network.cml").read_text()
    commands = [
        line.strip()
        for line in script.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    for line in commands:
        assert "av_clouds" not in line and "av_means" not in line, line


def test_two_dyes_are_still_solid_clouds():
    """The rule is about a *network*: `add_dye` on a pair keeps its surfaces."""
    ran = probe(
        """
app = open_app(size=(600, 400))
cmd, viewer = app.cmd, app.viewer
cmd.do("load 148l.pdb")
cmd.do("add_dye resi 119 and name CB, AV1 20 4.5 3.5")
cmd.do("add_dye resi 44 and name CB, AV1 20 4.5 3.5")
clouds = [e for e in viewer.objects.values() if getattr(e.state, "av", None) is not None]
emit("clouds", len(clouds))
emit("style", ",".join(sorted({
    str((e.state.volume_levels or [{}])[0].get("style", "")) for e in clouds
})))
emit("visible", sum(1 for e in clouds if e.visible))
""",
        timeout=600,
    )
    assert int(ran["clouds"]) == 2
    assert ran["style"] == "surface"
    assert int(ran["visible"]) == 2


# --------------------------------------------------------------------------- #
# Selecting a position, on the structure
# --------------------------------------------------------------------------- #
PICK = """
app = open_app(size=(900, 600))
cmd, gui, viewer = app.cmd, app.viewer.gui, app.viewer
cmd.do("demo t4l_network")
cmd.do("enable av_clouds")
app.renderer._draw()
panel = gui.panels.get("fps_circle")

def bead(position):
    oid = panel._object_for(position)
    state = viewer.objects[oid].state
    mean = viewer.objects[state.av_mean_object_id].state
    colour = tuple(round(float(c), 2) for c in
                   np.asarray(mean.colors_per_atom_override).ravel())
    return colour, round(float(np.asarray(mean.all_atom_radii).ravel()[0]), 2)

chosen = "119A"
partners = sorted(panel.partners(chosen))
other = [n for n in panel.model.positions
         if n != chosen and n not in partners][0]
emit("partners", ",".join(partners))
emit("before", "%s|%s" % bead(chosen))

panel.select(chosen)
app.renderer._draw()
emit("selected", "%s|%s" % bead(chosen))
emit("partner", "%s|%s" % bead(partners[0]))
emit("other", "%s|%s" % bead(other))

widths = {}
for name, fields in viewer.measurements.items():
    pair = panel._pair_of(name, fields)
    if chosen in pair:
        widths.setdefault("mine", set()).add(round(float(fields.get("width", 0)), 1))
    elif set(pair) & set(panel.model.positions):
        widths.setdefault("theirs", set()).add(round(float(fields.get("width", 0)), 1))
emit("width_mine", ",".join(str(w) for w in sorted(widths.get("mine", ()))))
emit("width_theirs", ",".join(str(w) for w in sorted(widths.get("theirs", ()))))

# ...and the scene really draws them that thick.
drawn = {}
for obj in (getattr(viewer._scene, "objects", None) or ()):
    if "meas_line" in str(obj.id):
        drawn.setdefault(round(float((obj.geometry.meta or {}).get("width", 0)), 1), 0)
        drawn[round(float((obj.geometry.meta or {}).get("width", 0)), 1)] += 1
emit("drawn_widths", ",".join(f"{w}x{n}" for w, n in sorted(drawn.items())))

panel.select(None)
app.renderer._draw()
emit("after", "%s|%s" % bead(chosen))
"""


@pytest.fixture(scope="module")
def picked():
    return probe("import numpy as np\n" + PICK, timeout=900)


def _colour_and_size(text: str):
    colour, _, size = text.partition("|")
    return eval(colour), float(size)  # noqa: S307 - our own emitted tuple


def test_the_selected_position_is_magenta_and_bigger(picked):
    from chimol.plugins.labelling.circle_window import SELECTED, _scene_colour

    colour, size = _colour_and_size(picked["selected"])
    _before, before_size = _colour_and_size(picked["before"])
    assert colour[:3] == pytest.approx(_scene_colour(SELECTED)[:3], abs=0.01)
    assert size > before_size, "the selected marker did not grow"


def test_its_partners_are_cyan_and_the_rest_grey(picked):
    from chimol.plugins.labelling.circle_window import MUTED, PARTNER, _scene_colour

    partner, partner_size = _colour_and_size(picked["partner"])
    other, other_size = _colour_and_size(picked["other"])
    assert partner[:3] == pytest.approx(_scene_colour(PARTNER)[:3], abs=0.01)
    assert other[:3] == pytest.approx(_scene_colour(MUTED)[:3], abs=0.01)
    _selected, selected_size = _colour_and_size(picked["selected"])
    assert selected_size > partner_size > other_size, "the three roles should be three sizes"


def test_the_selected_positions_distances_are_the_thick_ones(picked):
    mine = [float(w) for w in picked["width_mine"].split(",") if w]
    theirs = [float(w) for w in picked["width_theirs"].split(",") if w]
    assert mine and theirs
    assert min(mine) > max(theirs) * 1.5


def test_the_scene_draws_the_lines_that_thick(picked):
    """A width on a measurement that the renderer ignores is a width nobody sees."""
    drawn = dict(
        (float(part.split("x")[0]), int(part.split("x")[1]))
        for part in picked["drawn_widths"].split(",")
        if part
    )
    assert drawn, "no measurement lines were drawn at all"
    assert max(drawn) > min(drawn), "every line was drawn the same width"


def test_clearing_the_selection_puts_the_scene_back(picked):
    assert picked["after"] == picked["before"]
