"""The style list is kept between frames and listed again when a style folder changes."""


def test_styles_are_kept_and_follow_the_user_folder(tmp_path, monkeypatch):
    import os

    from chisurf.core.settings import theme

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    (tmp_path / "styles").mkdir()
    theme._STYLES_CACHE = None
    monkeypatch.setattr(theme, "STYLES_RECHECK_S", 0.0)  # the folders looked at every call
    first = theme.available_styles()
    assert first == theme._list_styles()
    calls = []
    real = theme._list_styles
    monkeypatch.setattr(theme, "_list_styles", lambda: calls.append(1) or real())
    assert theme.available_styles() == first and calls == []  # kept: nothing listed again
    sheet = tmp_path / "styles" / "my_own.css"
    sheet.write_text("/* */")
    folder = tmp_path / "styles"
    stamp = folder.stat().st_mtime_ns
    os.utime(folder, ns=(stamp + 10**9, stamp + 10**9))  # a coarse-clock file system too
    assert "my_own.css" in theme.available_styles() and calls == [1]
