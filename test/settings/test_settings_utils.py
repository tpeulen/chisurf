from __future__ import annotations

import yaml


def test_set_mmfdb_login_settings_persists_values(tmp_path, monkeypatch) -> None:
    """MMFDB login settings are merged into the user settings YAML."""
    from chisurf.core.settings import settings_utils

    settings_file = tmp_path / "settings_chisurf.yaml"
    settings_file.write_text(
        yaml.safe_dump(
            {
                "existing": True,
                "mmfdb": {
                    "autologin": False,
                    "default_user_id": "old_user",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_utils, "get_path", lambda name: tmp_path)

    saved = settings_utils.set_mmfdb_login_settings(
        {
            "autologin": True,
            "default_user_id": "admin_user",
            "save_login": True,
        }
    )

    data = yaml.safe_load(settings_file.read_text(encoding="utf-8"))
    assert saved is True
    assert data["existing"] is True
    assert data["mmfdb"]["autologin"] is True
    assert data["mmfdb"]["default_user_id"] == "admin_user"
    assert data["mmfdb"]["save_login"] is True


def test_set_language_persists_without_an_existing_gui_section(tmp_path, monkeypatch) -> None:
    """The UI language survives a restart even when the YAML has no ``gui:`` yet.

    Regression guard: the writer used to take ``data.get('gui', {})``, whose
    default is an *orphan* dict that is never attached to ``data`` — so on a
    settings file without a ``gui`` section the language was written into
    nothing and the choice silently reverted on the next start.
    """
    from chisurf.core.settings import settings_utils

    settings_file = tmp_path / "settings_chisurf.yaml"
    settings_file.write_text(yaml.safe_dump({"existing": True}), encoding="utf-8")
    monkeypatch.setattr(settings_utils, "get_path", lambda name: tmp_path)

    assert settings_utils.set_language("ru") is True

    data = yaml.safe_load(settings_file.read_text(encoding="utf-8"))
    assert data["existing"] is True
    assert data["gui"]["language"] == "ru"


def test_set_language_keeps_the_rest_of_the_gui_section(tmp_path, monkeypatch) -> None:
    """Writing the language merges into ``gui:`` instead of replacing it."""
    from chisurf.core.settings import settings_utils

    settings_file = tmp_path / "settings_chisurf.yaml"
    settings_file.write_text(
        yaml.safe_dump({"gui": {"language": "en", "use_ribbon_interface": True}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_utils, "get_path", lambda name: tmp_path)

    assert settings_utils.set_language("ru") is True

    data = yaml.safe_load(settings_file.read_text(encoding="utf-8"))
    assert data["gui"]["language"] == "ru"
    assert data["gui"]["use_ribbon_interface"] is True
