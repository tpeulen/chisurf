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

import pytest

import chimol
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
        line for line in STRUCTURE.read_text().splitlines()
        if line.startswith(("ATOM  ", "HETATM"))
    ]
    for name, fields in document["Positions"].items():
        residue = int(fields["residue_seq_number"])
        wanted = str(fields["atom_name"]).strip()
        chain = str(fields["chain_identifier"]).strip()
        assert any(
            line[21] == chain
            and int(line[22:26]) == residue
            and line[12:16].strip() == wanted
            for line in atoms
        ), f"{name}: no {wanted} on residue {residue} of chain {chain}"


# --------------------------------------------------------------------------- #
# What the demo builds
# --------------------------------------------------------------------------- #
SCRIPT = '''
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
'''


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
    assert int(ran["datasets"]) == 8          # every distance, then seven sets
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
LOOK = '''
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
'''


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
    assert float(look["cloud_alpha"]) > 0.3, (
        "a wireframe faded like a surface disappears"
    )


def test_the_demo_starts_with_the_structure_visible(look):
    """The clouds are there, switched off, one click from being back."""
    assert int(look["clouds_visible"]) == 0


def test_two_dyes_are_still_solid_clouds():
    """The rule is about a *network*: `add_dye` on a pair keeps its surfaces."""
    ran = probe('''
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
''', timeout=600)
    assert int(ran["clouds"]) == 2
    assert ran["style"] == "surface"
    assert int(ran["visible"]) == 2
