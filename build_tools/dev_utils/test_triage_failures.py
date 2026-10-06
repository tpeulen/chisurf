"""JUnit fixtures exercise triage ownership, node identity and CLI output."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from build_tools.dev_utils import triage_failures as triage


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Provide manifest ids that differ from their directory names."""
    for directory, plugin_id in (("burst/selector", "burst_selection"),
                                 ("core/pto_inspector", "container_browser")):
        path = tmp_path / "chisurf/plugins" / directory / "manifest.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"id": plugin_id}), encoding="utf-8")
    return tmp_path


def _xml(root: Path, contents: str) -> Path:
    """Write a genuine XML report consumed by the public parser."""
    path = root / "junit.xml"
    path.write_text(contents, encoding="utf-8")
    return path


def test_three_case_report_routes_burst_schema_and_unknown(repo):
    """The approved three-case report retains plugin and parameter context."""
    path = _xml(repo, """<testsuites><testsuite name="pytest">
      <testcase classname="chisurf.plugins.burst.selector.test.test_click.TestButton"
        file="chisurf/plugins/burst/selector/test/test_click.py" name="test_run[fast|slow]">
        <failure message="button failed">AssertionError</failure>
      </testcase>
      <testcase classname="test.test_ui_schemas" name="test_view[burst_selection]">
        <failure message="schema drift"/>
      </testcase>
      <testcase classname="test.test_misc.TestExample" file="test/test_misc.py"
        name="test_unowned"><failure/></testcase>
      <testcase classname="test.test_green" name="test_pass"/>
      <testcase classname="test.test_skip" name="test_skip"><skipped/></testcase>
    </testsuite></testsuites>""")
    failures = triage.parse_failures(path, repo)
    assert [case.workstream for case in failures] == ["W6b", "W7", "unassigned"]
    assert failures[0].node_id == (
        "chisurf/plugins/burst/selector/test/test_click.py::TestButton::test_run[fast|slow]"
    )
    assert failures[0].plugin_id == "burst_selection"
    assert failures[1].node_id == "test/test_ui_schemas.py::test_view[burst_selection]"
    assert failures[1].plugin_id == "burst_selection"
    report = triage.markdown_report(failures)
    assert "| W6b | 1 |" in report
    assert "| W7 | 1 |" in report
    assert "| unassigned | 1 |" in report
    assert "test_run[fast\\|slow]" in report
    assert "burst_selection" in report


@pytest.mark.parametrize(("file", "owner"), [
    ("chisurf/plugins/core/pto_inspector/test/test_open.py", "W4"),
    ("chisurf/plugins/core/sampling/test/test_chain.py", "W3"),
    ("chisurf/core/fio/test_reader.py", "W4"),
    ("test/fio/test_reader.py", "W4"),
    ("test/core/test_fit_group.py", "W3"),
    ("test/fitting/test_sampling_chain.py", "W3"),
    ("test/gui/test_global_fit_redraw.py", "W3"),
    ("test/e2e/test_pto_inspector.py", "W7"),
    ("modules/mmfdb/tests/test_core.py", "W13"),
    ("okf/test_links.py", "W0"),
    ("chisurf/plugins/tttr/tool/test/test_run.py", "W6a"),
    ("chisurf/plugins/microscopy/tool/test/test_run.py", "W6c"),
    ("chisurf/plugins/structure/tool/test/test_run.py", "W6d"),
    ("chisurf/plugins/fluorescence_decay/tool/test/test_run.py", "W6e"),
    ("chisurf/plugins/core/help/test/test_run.py", "W6f"),
    ("test/test_ui_schemas.py_extra", "unassigned"),
])
def test_specific_owner_takes_precedence_over_plugin_family(repo, file, owner):
    """Container, sampling and harness ownership wins over broad families."""
    path = _xml(repo, f'<testsuite><testcase file="{file}" name="test_case">'
                '<error message="setup failed"/></testcase></testsuite>')
    assert triage.parse_failures(path, repo)[0].workstream == owner


def test_namespace_nested_suites_and_multiple_outcomes_count_one_case(repo):
    """Setup/teardown errors are retained without double-counting a testcase."""
    path = _xml(repo, """<testsuites xmlns="urn:junit"><testsuite><testsuite>
      <testcase classname="test.core.test_fit_group.TestGlobal" name="test_model[1]">
        <failure/><error message="teardown failed"/>
      </testcase>
    </testsuite></testsuite></testsuites>""")
    failures = triage.parse_failures(path, repo)
    assert len(failures) == 1
    assert failures[0].outcomes == ("failure", "error")
    assert failures[0].node_id == "test/core/test_fit_group.py::TestGlobal::test_model[1]"
    report = triage.markdown_report(failures)
    assert "| W3 | 1 |" in report
    assert "FitGroup.model" in report and "_model" in report


def test_absolute_and_windows_paths_preserve_full_node_ids(repo):
    """File metadata remains authoritative when classnames use relative modules."""
    file = (repo / "chisurf/plugins/core/pto_inspector/test/test_open.py").as_posix()
    path = _xml(repo, f'<testsuite><testcase file="{file}" '
                'classname="chisurf.plugins.core.pto_inspector.test.test_open.TestOpen" '
                'name="test_file[set 1]"><error/></testcase>'
                '<testcase file="test\\test_ui_schemas.py" classname="test.test_ui_schemas" '
                'name="test_section[value]"><failure/></testcase></testsuite>')
    failures = triage.parse_failures(path, repo)
    assert failures[0].node_id == (
        "chisurf/plugins/core/pto_inspector/test/test_open.py::TestOpen::test_file[set 1]"
    )
    assert failures[0].workstream == "W4"
    assert failures[0].plugin_id == "container_browser"
    assert failures[1].node_id == "test/test_ui_schemas.py::test_section[value]"
    assert failures[1].workstream == "W7"


def test_explicit_node_id_is_not_truncated(repo):
    """Some report producers place an already complete node id in name."""
    node = "test/test_unknown.py::TestCases::test_case[value`with`quotes]"
    path = _xml(repo, f'<testsuite><testcase name="{node}"><error/></testcase></testsuite>')
    failures = triage.parse_failures(path, repo)
    assert failures[0].node_id == node
    assert "`` " + node + " ``" in triage.markdown_report(failures)


def test_uppercase_package_is_not_mistaken_for_a_test_class(repo):
    """Module names such as IMP remain part of the reconstructed file path."""
    path = _xml(repo, '<testsuite><testcase classname="IMP.bff.test.test_fit.TestCase" '
                'name="test_fit[1]"><failure/></testcase></testsuite>')
    assert triage.parse_failures(path, repo)[0].node_id == (
        "IMP/bff/test/test_fit.py::TestCase::test_fit[1]"
    )


def test_cli_prints_and_optionally_writes_identical_report(repo, monkeypatch, capsys):
    """The optional output path receives exactly the stdout report."""
    path = _xml(repo, '<testsuite><testcase file="test/test_ui_schemas.py" name="test_view">'
                '<failure/></testcase></testsuite>')
    monkeypatch.setattr(triage, "_manifests", lambda root: {})
    output = repo / "reports" / "triage.md"
    assert triage.main(["--junit", str(path), "--write", str(output)]) == 0
    assert output.read_text(encoding="utf-8") == capsys.readouterr().out
    assert triage.main(["--junit", str(path)]) == 0
    assert "| W7 | 1 |" in capsys.readouterr().out


def test_cli_reports_invalid_xml_without_a_traceback(repo, monkeypatch, capsys):
    """A malformed input report causes a useful nonzero CLI result."""
    path = _xml(repo, "<testsuite>")
    monkeypatch.setattr(triage, "_manifests", lambda root: {})
    with pytest.raises(SystemExit) as error:
        triage.main(["--junit", str(path)])
    assert error.value.code == 2
    stderr = capsys.readouterr().err
    assert "error:" in stderr
    assert "Traceback" not in stderr
