"""The legacy burst-companion column names resolve to dictionary terms without a sample.

``rename_columns`` maps the headers of ``.bur``/``.bg4``/``.br4`` files onto the
``mmfdb_burst_column`` vocabulary. The red-channel MLE results of a ``.br4`` companion were
reported as unmapped while their green twins resolved, because the dictionary had no red items.
"""

from chisurf.core.fio.fluorescence.burstwise_import import dictionary_columns, rename_columns


def test_the_red_mle_columns_are_dictionary_terms():
    d = dictionary_columns()
    for name, term in (
        ("Tau (red)", "tau_red"),
        ("2I*  (red)", "two_istar_red"),
        ("gamma (red)", "gamma_red"),
        ("r0 (red)", "r0_red"),
        ("rho (red)", "rho_red"),
    ):
        assert d[name]["term"] == f"_mmfdb_burst_column.{term}"
    renames, unmapped = rename_columns(
        ["Tau (red)", "2I* (red)", "gamma (red)", "r0 (red)", "rho (red)", "Tau  (red)"], d
    )
    assert renames == {"2I* (red)": "2I*  (red)", "Tau  (red)": "Tau (red)"}
    assert unmapped == []


def test_an_unknown_column_is_flagged_not_coined():
    renames, unmapped = rename_columns(["Something New", "First Photon"])
    assert renames == {} and unmapped == ["Something New"]
