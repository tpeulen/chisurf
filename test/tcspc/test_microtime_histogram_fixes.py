"""Keep the independent fortune-cookie regression while retiring print-only wizard checks."""


def test_message_box_fortune(monkeypatch):
    """A broken fortune cookie must not take the message box down with it."""
    import chisurf as cs
    from chisurf.gui.dialogs import ChiSurfMessageBox
    from chisurf.gui.widgets import fortune

    monkeypatch.setitem(cs.core.settings.cs_settings, "fortune", True)

    def _boom():
        raise UnicodeDecodeError("utf-8", b"", 0, 1, "bad byte")

    monkeypatch.setattr(fortune, "get_fortune", _boom)
    # The informative text survives unchanged rather than propagating the error.
    assert ChiSurfMessageBox._fortune("Reading settings and file.") == "Reading settings and file."

    monkeypatch.setattr(fortune, "get_fortune", lambda: "")
    assert ChiSurfMessageBox._fortune(None) is None

    monkeypatch.setattr(fortune, "get_fortune", lambda: "Fortune favours the bold.")
    assert ChiSurfMessageBox._fortune(None) == "Fortune favours the bold."
    assert ChiSurfMessageBox._fortune("Info.").startswith("Info.")
