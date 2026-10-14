"""Keep the independent fortune-cookie regression while retiring print-only wizard checks."""


def test_message_box_fortune(monkeypatch):
    """A broken fortune cookie must not take the message box down with it."""
    import chisurf as cs
    from chisurf.gui.dialogs import ChiSurfMessageBox
    from chisurf.gui.widgets import fortune

    monkeypatch.setitem(cs.core.settings.cs_settings, "fortune", True)

    def _boom(**_kwargs):
        raise UnicodeDecodeError("utf-8", b"", 0, 1, "bad byte")

    monkeypatch.setattr(fortune, "get_fortune", _boom)
    # The informative text survives unchanged rather than propagating the error.
    assert ChiSurfMessageBox._fortune("Reading settings and file.") == "Reading settings and file."

    monkeypatch.setattr(fortune, "get_fortune", lambda **_kwargs: "")
    assert ChiSurfMessageBox._fortune(None) is None

    monkeypatch.setattr(fortune, "get_fortune", lambda **_kwargs: "Fortune favours the bold.")
    assert ChiSurfMessageBox._fortune(None) == "Fortune favours the bold."
    assert ChiSurfMessageBox._fortune("Info.").startswith("Info.")


def test_message_box_fortune_reads_the_settings_block(monkeypatch):
    """The shipped ``fortune`` block switches the cookie off and passes its limits on.

    A truth test on the block itself was always true, so ``enabled: false`` was
    ignored and ``attempts``/``min_length``/``max_length`` never reached the picker.
    """
    import chisurf as cs
    from chisurf.gui.dialogs import ChiSurfMessageBox
    from chisurf.gui.widgets import fortune

    seen = {}

    def _record(**kwargs):
        seen.update(kwargs)
        return "A saying."

    monkeypatch.setattr(fortune, "get_fortune", _record)
    monkeypatch.setitem(
        cs.core.settings.cs_settings,
        "fortune",
        {"enabled": False, "attempts": 7, "min_length": 3, "max_length": 300},
    )
    assert ChiSurfMessageBox._fortune("Info.") == "Info."
    assert not seen

    monkeypatch.setitem(
        cs.core.settings.cs_settings,
        "fortune",
        {"enabled": True, "attempts": 7, "min_length": 3, "max_length": 300},
    )
    assert ChiSurfMessageBox._fortune("Info.") == "Info.\n\nA saying."
    assert seen == {"min_length": 3, "max_length": 300, "maximum_number_of_attempts": 7}
