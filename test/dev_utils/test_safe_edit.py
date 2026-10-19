"""Tests for ``build_tools.dev_utils.safe_edit`` (shared-file edits must not destroy data)."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

import pytest

from build_tools.dev_utils import safe_edit as se

LOG = "# Update Log\n\n## 2026-10-13\n\n- a\n- b\n\n## 2026-10-12\n\n- c\n"

TS = (
    '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n<TS version="2.1">\n'
    "    <context>\n        <name>A</name>\n"
    '        <message>\n            <location filename="x.py" line="3" />\n'
    "            <source>Yes &amp; no</source>\n"
    '            <translation type="unfinished"></translation>\n        </message>\n'
    "        <message>\n            <source>Keep</source>\n"
    "            <translation>Behalte  </translation>\n        </message>\n"
    "    </context>\n"
    "    <context>\n        <name>B</name>\n"
    "        <message>\n            <source>Other</source>\n"
    "            <translation>Anderes</translation>\n        </message>\n"
    "    </context>\n</TS>\n"
)


def _messages(text):
    return {
        (c.findtext("name"), m.findtext("source")): ET.tostring(m, encoding="unicode").strip()
        for c in ET.fromstring(text).findall("context")
        for m in c.findall("message")
    }


def test_edit_is_atomic_and_leaves_no_temp(tmp_path):
    f = tmp_path / "f.md"
    f.write_text("hello\n")

    def boom(old):
        raise RuntimeError("script bug")

    with pytest.raises(RuntimeError):
        se.edit_file(f, boom)
    assert f.read_text() == "hello\n"
    assert se.edit_file(f, lambda o: o + "world\n") is True
    assert f.read_text() == "hello\nworld\n"
    assert os.listdir(tmp_path) == ["f.md"]
    assert se.edit_file(f, lambda o: o) is False


def test_edit_follows_symlink(tmp_path):
    real = tmp_path / "real.md"
    real.write_text("x\n")
    link = tmp_path / "link.md"
    link.symlink_to(real)
    se.edit_file(link, lambda o: o + "y\n")
    assert link.is_symlink() and real.read_text() == "x\ny\n"


def test_shrink_and_empty_refused(tmp_path):
    f = tmp_path / "f.md"
    f.write_text("0123456789" * 10)
    with pytest.raises(se.UnsafeEditError):
        se.edit_file(f, lambda o: "")
    with pytest.raises(se.UnsafeEditError):
        se.edit_file(f, lambda o: o[:50])
    assert f.read_text() == "0123456789" * 10
    assert se.edit_file(f, lambda o: o[:90]) is True
    assert se.edit_file(f, lambda o: o[:10], allow_shrink=True) is True
    assert se.edit_file(f, lambda o: "", allow_shrink=True) is True


def test_concurrent_change_is_detected(tmp_path):
    f = tmp_path / "f.md"
    f.write_text("a\n")

    def racing(old):
        f.write_text("someone else\n")
        return old + "b\n"

    with pytest.raises(se.UnsafeEditError):
        se.edit_file(f, racing)
    assert f.read_text() == "someone else\n"


def test_log_bullet_reuses_heading(tmp_path):
    f = tmp_path / "log.md"
    f.write_text(LOG)
    se.append_log_bullet("new one", "2026-10-13", path=f)
    se.append_log_bullet("- newer", "2026-10-13", path=f)
    out = f.read_text()
    assert out.count("## 2026-10-13") == 1
    assert "- b\n- new one\n- newer\n\n## 2026-10-12" in out
    assert out.endswith("- c\n")


def test_log_bullet_creates_heading_once(tmp_path):
    f = tmp_path / "log.md"
    f.write_text(LOG)
    se.append_log_bullet("x", "2026-10-14", path=f)
    se.append_log_bullet("y", "2026-10-14", path=f)
    out = f.read_text()
    assert out.count("## 2026-10-14") == 1
    assert out.index("## 2026-10-14") < out.index("## 2026-10-13")
    assert "- x\n- y\n\n## 2026-10-13" in out


def test_merge_duplicate_headings():
    dup = "# Update Log\n\n## 2026-10-13\n\n- a\n\n## 2026-10-13\n\n- b\n\n## 2026-10-12\n\n- c\n"
    out = se.merge_duplicate_headings(dup)
    assert out == "# Update Log\n\n## 2026-10-13\n\n- a\n- b\n\n## 2026-10-12\n\n- c\n"
    assert se.merge_duplicate_headings(out) == out


def test_ts_roundtrip_leaves_untouched_entries(tmp_path):
    f = tmp_path / "chisurf_de.ts"
    f.write_text(TS, encoding="utf-8")
    before = _messages(TS)
    se.add_ts_entries(
        "de",
        [("A", "Yes & no", "Ja & nein"), ("B", "New", "Neu"), ("C", "<b>", "fett")],
        directory=tmp_path,
    )
    out = f.read_text(encoding="utf-8")
    after = _messages(out)
    assert "Behalte  " in out  # untouched bytes, trailing spaces included
    assert after[("A", "Keep")] == before[("A", "Keep")]
    assert after[("B", "Other")] == before[("B", "Other")]
    assert ET.fromstring(after[("A", "Yes & no")]).findtext("translation") == "Ja & nein"
    assert 'type="unfinished"' not in after[("A", "Yes & no")]
    assert "x.py" in after[("A", "Yes & no")]  # location kept
    assert ET.fromstring(after[("B", "New")]).findtext("translation") == "Neu"
    assert ET.fromstring(after[("C", "<b>")]).findtext("translation") == "fett"
    assert se.add_ts_entries("de", [], directory=tmp_path) is False
    assert f.read_text(encoding="utf-8") == out


def test_ts_missing_file_is_not_created(tmp_path):
    with pytest.raises(FileNotFoundError):
        se.add_ts_entries("xx", [("A", "s", "t")], directory=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_real_catalogue_noop_roundtrip():
    """The real ``de`` catalogue parses and an entry-free edit leaves it byte-identical."""
    path = se.I18N_DIR / "chisurf_de.ts"
    before = path.read_bytes()
    assert se.add_ts_entries("de", []) is False
    assert path.read_bytes() == before
