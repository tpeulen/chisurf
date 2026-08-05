"""An ordered, named list of regions — what every ROI GUI actually edits.

Three tools grew their own version of this list and disagreed about it: the CLSM
tool could not combine two regions although the core supports ``&``/``|``/``~``;
ndX's carried ``enabled`` and ``invert`` per member, combined by implicit
AND, in the opposite mask convention, and dropped every non-rectangle selection
on reload; the MLE tools silently unioned whatever a file contained. These tests
pin the one type behind all three.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.roi import (
    EllipseROI,
    PolygonROI,
    RectangleROI,
    RegionCollection,
    RegionEntry,
    save_rois,
)

#: Points to probe with: inside-left, inside-right, and the gap between them.
LEFT, RIGHT, MIDDLE = (5.0, 5.0), (25.0, 25.0), (15.0, 15.0)


def _collection(combine="or"):
    c = RegionCollection(combine=combine)
    c.add(RectangleROI(0, 0, 10, 10, name="left"))
    c.add(RectangleROI(20, 20, 30, 30, name="right"))
    return c


def _hits(collection, *points):
    return collection.contains(np.array(points)).tolist()


def test_a_union_covers_both_regions_and_not_the_gap():
    assert _hits(_collection("or"), LEFT, RIGHT, MIDDLE) == [True, True, False]


def test_an_intersection_of_disjoint_regions_selects_nothing():
    """"and" is the default because stacked gates narrow; here that means empty."""
    assert _hits(_collection("and"), LEFT, RIGHT, MIDDLE) == [False, False, False]


def test_disabling_keeps_the_region_but_drops_it_from_the_answer():
    """Switching a region off to see what it did is the commonest edit."""
    c = _collection("or")
    c.set_enabled("right", False)
    assert _hits(c, LEFT, RIGHT) == [True, False]
    assert len(c) == 2 and "right" in c


def test_inverting_contributes_the_complement_without_wrapping_the_region():
    """The geometry stays editable after the toggle — that is why it is a flag."""
    c = RegionCollection(combine="and")
    c.add(RectangleROI(0, 0, 30, 30, name="field"))
    c.add(RectangleROI(10, 10, 20, 20, name="hole"), invert=True)
    assert _hits(c, (5.0, 5.0), (15.0, 15.0)) == [True, False]
    assert isinstance(c.roi("hole"), RectangleROI)

    c.set_invert("hole", False)
    assert _hits(c, (15.0, 15.0)) == [True]


def test_nothing_enabled_is_not_the_same_as_no_restriction():
    """``combined()`` says None; the mask/contains conveniences say everything.

    A caller that treats "no region" as "the whole frame" must do so knowingly:
    returning an all-true region from ``combined()`` would make an empty
    collection indistinguishable from one whose regions were deliberately
    switched off.
    """
    c = _collection("or")
    for name in c.names:
        c.set_enabled(name, False)

    assert c.combined() is None
    assert _hits(c, LEFT, MIDDLE) == [True, True]
    assert c.to_mask((4, 4)).all()


def test_the_exclusion_mask_is_the_complement_of_containment():
    """ndX's convention, named rather than remembered."""
    c = _collection("or")
    points = np.array([LEFT, MIDDLE])
    assert c.excluded(points).tolist() == [False, True]
    np.testing.assert_array_equal(c.excluded(points), ~c.contains(points))


def test_a_single_enabled_region_is_returned_as_itself():
    """No pointless CompositeROI wrapper around one region."""
    c = _collection("or")
    c.set_enabled("right", False)
    assert isinstance(c.combined(), RectangleROI)


# --- names -------------------------------------------------------------------
def test_a_taken_name_is_suffixed_rather_than_shadowing():
    """Two rows reading "cell" is worse than "cell (2)"."""
    c = RegionCollection()
    assert c.add(RectangleROI(0, 0, 1, 1, name="cell")) == "cell"
    assert c.add(RectangleROI(2, 2, 3, 3, name="cell")) == "cell (2)"
    assert c.add(RectangleROI(4, 4, 5, 5, name="cell")) == "cell (3)"
    assert len(c) == 3


def test_renaming_also_avoids_a_collision():
    c = _collection()
    assert c.rename("left", "right") == "right (2)"
    assert set(c.names) == {"right", "right (2)"}


def test_reordering_moves_a_region_without_losing_it():
    c = _collection()
    c.move("right", 0)
    assert c.names == ["right", "left"]


def test_removing_reports_whether_it_was_there():
    c = _collection()
    assert c.remove("left") is True
    assert c.remove("left") is False
    assert c.names == ["right"]


# --- serialisation ------------------------------------------------------------
def test_a_round_trip_keeps_geometry_flags_and_order():
    """ndX's loader kept only rectangles; every shape and flag must survive."""
    c = RegionCollection(combine="xor", name="gate")
    c.add(RectangleROI(0, 0, 10, 10, name="rect"))
    c.add(EllipseROI(20.0, 20.0, 5.0, 3.0, name="ellipse"), enabled=False)
    c.add(PolygonROI([(0, 0), (5, 0), (5, 5)], name="poly"), invert=True)

    back = RegionCollection.from_dict(c.to_dict())

    assert back.combine == "xor" and back.name == "gate"
    assert back.names == ["rect", "ellipse", "poly"]
    assert isinstance(back.roi("ellipse"), EllipseROI)
    assert isinstance(back.roi("poly"), PolygonROI)
    assert back["ellipse"].enabled is False
    assert back["poly"].invert is True


def test_saving_and_loading_a_collection_file(tmp_path):
    c = _collection("xor")
    c.set_enabled("left", False)
    path = c.save(str(tmp_path / "regions.json"))

    back = RegionCollection.load(path)
    assert back.combine == "xor"
    assert back["left"].enabled is False
    assert back.names == ["left", "right"]


def test_a_plain_regions_file_loads_as_a_union(tmp_path):
    """A file of separately drawn objects means "any of these", not "all"."""
    path = tmp_path / "objects.json"
    save_rois(
        [RectangleROI(0, 0, 10, 10, name="a"), RectangleROI(20, 20, 30, 30, name="b")],
        str(path),
    )
    back = RegionCollection.load(str(path))
    assert back.combine == "or"
    assert _hits(back, LEFT, RIGHT, MIDDLE) == [True, True, False]


def test_a_label_image_loads_as_one_entry_per_object(tmp_path):
    """A segmentation is many regions, not one merged blob."""
    from chisurf.core.fio.image import imread, imwrite

    labels = np.zeros((16, 16), dtype=np.uint16)
    labels[2:5, 2:5] = 1
    labels[9:13, 9:13] = 2
    path = tmp_path / "seg.tif"
    imwrite(str(path), labels)

    back = RegionCollection.load(str(path))
    assert len(back) == 2


# --- measuring ----------------------------------------------------------------
def test_every_region_is_measured_including_the_disabled_ones():
    """The list a user reads is the list they edit."""
    image = np.zeros((32, 32))
    image[0:10, 0:10] = 4.0
    c = _collection("or")
    c.set_enabled("right", False)

    props = c.properties(image.shape, image=image)
    assert len(props) == 2
    assert props[0].area == 100
    assert props[0].intensity_mean == pytest.approx(4.0)


def test_a_bad_combine_is_refused_at_the_point_of_setting():
    with pytest.raises(ValueError, match="unknown combine"):
        RegionCollection(combine="nand")
    c = RegionCollection()
    with pytest.raises(ValueError):
        c.combine = "sub"


def test_a_bare_mask_can_be_added_directly():
    """``as_roi`` accepts masks, so the collection does too."""
    mask = np.zeros((16, 16), dtype=bool)
    mask[2:6, 2:6] = True
    c = RegionCollection()
    name = c.add(mask, name="painted")
    assert name == "painted"
    assert c.to_mask((16, 16)).sum() == 16


def test_an_entry_exposes_the_name_of_its_region():
    """The name lives on the region, so it is not stored twice and cannot drift."""
    entry = RegionEntry(roi=RectangleROI(0, 0, 1, 1, name="a"))
    assert entry.name == "a"
    entry.name = "b"
    assert entry.roi.name == "b"


def test_a_collection_file_is_readable_by_the_shared_region_loaders(tmp_path):
    """The editor must not write a format only the editor can open.

    Every tool that confines an analysis takes a region file through
    ``load_regions``/``load_region``. A collection saved from the shared editor
    has to arrive there as its regions — the flags and the combining rule are
    what those loaders drop, not the geometry.
    """
    from chisurf.core.roi import load_region, load_regions

    c = _collection("or")
    c.set_enabled("right", False)
    path = str(tmp_path / "regions.json")
    c.save(path)

    assert [r.name for r in load_regions(path)] == ["left", "right"]
    # `load_region` unions them, disabled included: it reads regions, not state.
    united = load_region(path)
    assert united.contains(np.array([LEFT, RIGHT, MIDDLE])).tolist() == [True, True, False]


def test_entries_can_be_moved_between_collections_with_their_flags():
    """Merging two lists must not silently re-enable what was switched off."""
    source = _collection("or")
    source.set_enabled("right", False)
    source.set_invert("left", True)

    target = RegionCollection()
    target.extend(source)

    assert target.names == ["left", "right"]
    assert target["right"].enabled is False
    assert target["left"].invert is True
