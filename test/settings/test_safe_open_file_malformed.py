"""A malformed settings file must degrade to the default, not brick the import.

Pins RF-1003: ``safe_open_file`` guarded the *open* only, so a truncated quoted
scalar in the user ``settings_chisurf.yaml`` escaped as a raw
``yaml.scanner.ScannerError`` out of ``import chisurf.core.settings`` and took
the GUI, ``csc`` and the server down with it.
"""

from __future__ import annotations

import json

import pytest
import yaml

from chisurf.core.settings.file_utils import safe_open_file

BROKEN_YAML = 'gui:\n  plot_style: "unterminated\n'
BROKEN_JSON = '{"l1": 0.12, "l2":}'


def test_malformed_yaml_returns_default(tmp_path, capsys) -> None:
    """A YAML parse error is answered with ``default_value`` and a named path."""
    path = tmp_path / "settings_chisurf.yaml"
    path.write_text(BROKEN_YAML, encoding="utf-8")

    result = safe_open_file(file_path=path, processor=yaml.safe_load, default_value={})

    assert result == {}
    assert str(path) in capsys.readouterr().out


def test_malformed_json_returns_default(tmp_path, capsys) -> None:
    """A JSON decode error is answered with ``default_value`` and a named path."""
    path = tmp_path / "anisotropy_corrections.json"
    path.write_text(BROKEN_JSON, encoding="utf-8")

    result = safe_open_file(file_path=path, processor=json.load, default_value={"g_factor": 1.0})

    assert result == {"g_factor": 1.0}
    assert str(path) in capsys.readouterr().out


def test_undecodable_bytes_return_default(tmp_path) -> None:
    """``UnicodeDecodeError`` is a ``ValueError``, not an ``OSError`` — still caught."""
    path = tmp_path / "settings_chisurf.yaml"
    path.write_bytes(b"\xff\xfe\x00binary")

    assert safe_open_file(file_path=path, processor=yaml.safe_load, default_value={}) == {}


def test_missing_file_still_returns_default(tmp_path) -> None:
    """The pre-existing ``OSError`` behaviour is unchanged."""
    assert (
        safe_open_file(file_path=tmp_path / "absent.yaml", default_value="fallback") == "fallback"
    )


@pytest.mark.parametrize("use_source_folder", [False, True])
def test_corrupt_user_settings_fall_back_to_packaged(tmp_path, use_source_folder) -> None:
    """``get_chisurf_settings`` returns the packaged defaults for a corrupt user file."""
    from chisurf.core.settings import settings_utils

    settings_file = tmp_path / "settings_chisurf.yaml"
    settings_file.write_text(BROKEN_YAML, encoding="utf-8")

    data = settings_utils.get_chisurf_settings(settings_file, use_source_folder=use_source_folder)

    assert isinstance(data, dict)
    # The packaged file carries these; an unguarded parse error would have raised.
    assert "gui" in data
    assert "optimization" in data
