"""Tests for the AutoForm-based TTTR Header Editor tool."""

from __future__ import annotations

import json
import pathlib

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
_DATA = _REPO_ROOT / "test" / "data"
_PTU = _DATA / "clsm" / "Leica_SP5.ptu"
_HT3 = _DATA / "clsm" / "PQ_Olympus_MFIS.ht3"
_SPC = _DATA / "tttr" / "BH" / "132" / "BH_SPC132.spc"


def test_view_model_sample_and_json():
    from chisurf.plugins.tttr.tttr_header_edit.gui.view_model import HeaderEditorViewModel

    m = HeaderEditorViewModel()
    assert len(m.tags) == 6  # sample header
    assert m.json_text.strip().startswith("{")
    assert m.can_save() is not None  # no source file open
    assert "sample" in m.source_summary.lower()


def test_view_spec_loads():
    from chisurf.plugins.tttr.tttr_header_edit.gui.view_model import HeaderEditorViewModel

    assert HeaderEditorViewModel().view_spec() is not None


def test_tool_builds_with_autoform(qapp, qtbot):
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.registry import get_section_factory
    from chisurf.plugins.tttr.tttr_header_edit.gui.tool import TagsEditor

    w = TagsEditor()
    qtbot.addWidget(w)
    assert isinstance(w.auto_form, AutoForm)
    assert get_section_factory("header_table") is not None


@pytest.mark.parametrize(
    "path, container",
    [
        pytest.param(_PTU, "ptu", id="ptu"),
        pytest.param(_HT3, "ht3", id="ht3"),
        pytest.param(_SPC, "spc", id="spc"),
    ],
)
def test_load_file_reads_all_supported_formats(path, container):
    """Read PTU, HT3 and SPC through the one ``load_file`` path.

    tttrlib normalises every container into the same tag list.
    """
    if not path.exists():
        pytest.skip(f"sample {container} not available")
    from chisurf.plugins.tttr.tttr_header_edit.gui.view_model import HeaderEditorViewModel

    m = HeaderEditorViewModel()
    m.load_file(str(path))
    assert len(m.tags) > 0
    assert m.source_container == container
    assert m.can_save() is None
    assert container.upper() in m.source_summary


@pytest.mark.skipif(not _HT3.exists(), reason="sample HT3 not available")
def test_save_from_ht3_writes_ptu_with_edited_tags(tmp_path):
    """Save a header edited from a non-PTU source as a PTU.

    The written PTU round-trips the edited tags and preserves the photon events.
    """
    import tttrlib

    from chisurf.plugins.tttr.tttr_header_edit.gui.view_model import HeaderEditorViewModel

    n = len(tttrlib.TTTR(str(_HT3)))
    m = HeaderEditorViewModel()
    m.load_file(str(_HT3))

    rows = [
        {
            "name": t["name"],
            "type": m.TYPE_MAPPING.get(t["type"], ""),
            "value": t["value"],
            "idx": str(t.get("idx", -1)),
        }
        for t in m.tags
    ]
    rows.append({"name": "User_Author", "type": "AnsiString", "value": "EDITED", "idx": "-1"})
    m.set_tags(rows)

    out = tmp_path / "edited.ptu"
    m.save(str(out))
    back = tttrlib.TTTR(str(out))
    assert len(back) == n
    tags = json.loads(back.header.json)["tags"]
    author = [t for t in tags if t["name"] == "User_Author"]
    assert author and author[0]["value"] == "EDITED"


@pytest.mark.skipif(not _PTU.exists(), reason="sample PTU not available")
def test_header_roundtrip_preserves_tags_and_photons(tmp_path):
    import tttrlib

    from chisurf.plugins.tttr.tttr_header_edit.gui.view_model import HeaderEditorViewModel

    n = len(tttrlib.TTTR(str(_PTU)))
    m = HeaderEditorViewModel()
    m.load_file(str(_PTU))
    n_tags = len(m.tags)
    assert n_tags > 10

    # Rebuild rows exactly as the table would; round-trip must not drop tags.
    rows = [
        {
            "name": t["name"],
            "type": m.TYPE_MAPPING.get(t["type"], ""),
            "value": t["value"],
            "idx": str(t.get("idx", -1)),
        }
        for t in m.tags
    ]
    m.set_tags(rows)
    assert len(m.tags) == n_tags  # no silent drops in the view-model

    out = tmp_path / "edited.ptu"
    m.save(str(out))
    back = tttrlib.TTTR(str(out))
    assert len(back) == n
    # The PTU writer may add derived tags (e.g. MeasDesc_NumberMicrotimes), so
    # assert the original tag names survive as a superset rather than an exact count.
    src_names = {t["name"] for t in m.tags}
    back_names = {t["name"] for t in json.loads(back.header.json)["tags"]}
    assert src_names <= back_names
