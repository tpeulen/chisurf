"""Loading must succeed, or fail — never hang.

A reader that cannot read a file used to be reported by constructing a modal
error dialog from inside the macro layer. With a GUI that is fine. Without
one it is fatal: ``MyMessageBox.__init__`` calls ``exec_()``, which blocks
forever waiting for a click that will never come, and with no ``QApplication``
at all Qt aborts the process outright. Either way a head-less caller — the
CLI, a script, a test, the assistant — never gets an answer.
"""

from __future__ import annotations

import time

import pytest

from chisurf.core.agent import ToolError
from chisurf.core.agent.tools import data as data_tools
from test.agent.conftest import DATA_DIR

FCS_DIR = DATA_DIR / "fcs"


@pytest.fixture()
def context(clean_session, tmp_path):
    """Return a context rooted at a scratch directory."""
    from chisurf.core.agent import AgentContext

    return AgentContext(working_directory=str(tmp_path))


def test_an_unreadable_file_fails_instead_of_blocking(context, tmp_path):
    """The regression: this used to wait on an invisible modal dialog."""
    broken = tmp_path / "not_really_a_decay.dat"
    broken.write_bytes(b"\x00\x01\x02 this is not a decay \xff\xfe")

    started = time.perf_counter()
    with pytest.raises(ToolError):
        data_tools.load_data(context, paths=[broken.name])
    assert time.perf_counter() - started < 20.0, "loading blocked instead of failing"


def test_the_failure_names_the_file(context, tmp_path):
    broken = tmp_path / "bad.dat"
    broken.write_bytes(b"\x00\x01\x02")
    with pytest.raises(ToolError, match="bad.dat"):
        data_tools.load_data(context, paths=[broken.name])


def test_one_bad_file_does_not_stop_the_good_ones(context, tmp_path):
    """A folder with a dud in it still loads the rest."""
    import shutil

    shutil.copy(DATA_DIR / "tcspc" / "EasyTau300" / "215-268 D0.dat", tmp_path)
    (tmp_path / "broken.dat").write_bytes(b"\x00\x01\x02")

    result = data_tools.load_data(context, directory=".", pattern="*.dat")
    assert result["n_loaded"] == 1
    assert result["failures"], "the failure should be reported, not hidden"


# ── the readers themselves ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("folder", "pattern", "experiment", "reader"),
    [
        ("kristine", "*.cor", None, None),
        ("asc", "*.ASC", "FCS", "ALV-Correlator"),
        ("pycorrfit", "PyCorrFit_CC_A488.csv", "FCS", "PyCorrFit"),
        (
            "confocor3/Zeiss_Confocor3_LSM780_FCCS_HeLa_2015",
            "017_cp_KIND+BFA.fcs",
            None,
            None,
        ),
    ],
)
def test_a_correlation_reader_still_works(clean_session, folder, pattern, experiment, reader):
    """Three of these were dead: they used aliases NumPy 2 removed.

    ``np.float`` went in NumPy 1.24 and ``np.float_`` in 2.0, so the ALV,
    PyCorrFit and ConfoCor3 readers all raised ``AttributeError`` on the first
    line of data they parsed.
    """
    from chisurf.core.agent import AgentContext

    source = FCS_DIR / folder
    if not source.is_dir():
        pytest.skip(f"no sample data at {source}")

    context = AgentContext(working_directory=str(source))
    started = time.perf_counter()
    result = data_tools.load_data(
        context, directory=".", pattern=pattern, experiment=experiment, reader=reader
    )
    elapsed = time.perf_counter() - started

    assert result["n_loaded"] >= 1, f"{folder} loaded nothing"
    assert elapsed < 60.0, f"{folder} took {elapsed:.0f}s"


def test_no_numpy_aliases_removed_in_numpy_2_remain():
    """A guardrail: these fail only when the code path is reached."""
    import pathlib
    import re

    import chisurf

    removed = re.compile(r"\bnp\.(float|complex|unicode|object|str|bool8|NaN|Inf|infty)(?![\w.])")
    offenders: list[str] = []
    root = pathlib.Path(chisurf.__file__).parent
    # The compatibility shim exists to restore these names, so its prose names
    # them; scanning it would flag the fix rather than a use of the alias.
    exempt = {root / "core" / "compat.py"}
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts or "build" in path.parts or path in exempt:
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if removed.search(line):
                offenders.append(f"{path.relative_to(root)}:{number}")
    assert not offenders, f"aliases removed in NumPy 2 are still used: {offenders[:10]}"
