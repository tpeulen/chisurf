"""Two sources of truth for the display defaults, and a copy that never updates.

Chimol's defaults live twice: as a Python dict in `config.py` and as the shipped
`chimol_display.json`. The JSON is what is actually read; the dict only fills in
keys the JSON is missing. So editing the dict changes **nothing** for anyone, and
it does so quietly -- a whole afternoon's appearance work sat in the dict while
every render used the JSON's older values.

Worse, a user's copy in `~/.chisurf/` is written once and then never touched, so
even fixing the shipped file reaches nobody who already has one. The version
check meant to catch that existed but was never called from anywhere.

These tests hold both ends: the two default sources must agree, and a stale user
copy must pick up defaults it never deliberately changed.
"""
from __future__ import annotations

import json

import pytest

from chisurf.plugins.chimol.chimol import config as cfg_mod


@pytest.fixture(scope="module")
def shipped() -> dict:
    """Return the JSON that ships with the package."""
    path = cfg_mod.get_package_display_config_path()
    return json.loads(path.read_text(encoding="utf-8"))


def _python_defaults() -> dict:
    """Return the dict `_load_display_config` merges in for missing keys."""
    import inspect

    source = inspect.getsource(cfg_mod._load_display_config)
    assert "default = {" in source
    # Evaluated rather than duplicated: the point of the test is that the two
    # agree, so writing the values out a third time would defeat it.
    namespace: dict = {"DISPLAY_CONFIG_VERSION": cfg_mod.DISPLAY_CONFIG_VERSION}
    body = source.split("default = ", 1)[1]
    depth, end = 0, 0
    for index, char in enumerate(body):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    return eval(body[:end], namespace)  # noqa: S307 - our own source


def test_the_shipped_json_and_the_python_defaults_agree(shipped):
    """A value that differs between them is dead configuration.

    The JSON wins at runtime, so a Python default that disagrees is never used
    and silently misleads whoever edits it -- which is exactly what happened to
    the metaball material.
    """
    defaults = _python_defaults()
    mismatches = []
    for section, block in defaults.items():
        if section == "_version" or not isinstance(block, dict):
            continue
        shipped_block = shipped.get(section)
        if not isinstance(shipped_block, dict):
            continue
        for key, value in block.items():
            if key not in shipped_block:
                continue
            if shipped_block[key] != value:
                mismatches.append(
                    f"{section}.{key}: json={shipped_block[key]!r} python={value!r}"
                )
    assert not mismatches, "defaults disagree:\n  " + "\n  ".join(mismatches)


def test_the_shipped_config_carries_the_current_version(shipped):
    """Otherwise no user copy is ever recognised as out of date."""
    assert shipped.get("_version") == cfg_mod.DISPLAY_CONFIG_VERSION


def test_every_migration_matches_the_shipped_value(shipped):
    """A migration's *new* value must be what the package actually ships.

    A migration that moved a user to a value the package does not use would
    leave the two disagreeing again, one user at a time.
    """
    # Migrations chain: a key may move twice (2.2 -> 2.8 -> 6.5), and only the
    # *last* step has to match what ships. Checking every step would forbid ever
    # changing a default twice.
    final: dict[tuple[str, str], object] = {}
    for version in sorted(cfg_mod.DISPLAY_CONFIG_MIGRATIONS):
        assert version <= cfg_mod.DISPLAY_CONFIG_VERSION, (
            f"migration {version} is newer than DISPLAY_CONFIG_VERSION"
        )
        for section, keys in cfg_mod.DISPLAY_CONFIG_MIGRATIONS[version].items():
            for key, (_old, new_value) in keys.items():
                final[(section, key)] = new_value

    wrong = []
    for (section, key), new_value in final.items():
        shipped_value = shipped.get(section, {}).get(key)
        if shipped_value != new_value:
            wrong.append(f"{section}.{key}: shipped={shipped_value!r} new={new_value!r}")
    assert not wrong, "migrations disagree with the shipped config:\n  " + "\n  ".join(wrong)


def test_a_chained_migration_lands_on_the_current_default(shipped):
    """A copy old enough to need several steps ends on the newest value.

    `sigma_factor` has moved 2.2 -> 2.8 -> 6.5 -> 4.0 across four versions, and
    it went *up* and then back down: someone who never opened the app in between
    must still arrive at what ships today, and someone who stopped part-way must
    be carried the rest of the way. Asserted against the shipped file rather
    than a literal, so the next change to this default does not have to edit the
    test -- only the migration table.
    """
    current = shipped["metaball"]["sigma_factor"]

    for start_version, start_value in ((0, 2.2), (4, 2.8), (5, 6.5)):
        stale = {"metaball": {"sigma_factor": start_value}}
        cfg_mod.apply_display_config_migrations(stale, from_version=start_version)
        assert stale["metaball"]["sigma_factor"] == current, (
            f"a copy at version {start_version} did not reach the shipped value"
        )


# --------------------------------------------------------------------------- #
# Migrating a user's copy
# --------------------------------------------------------------------------- #
def test_an_untouched_default_is_brought_forward():
    """The value the user never changed follows the package."""
    user = {"metaball": {"shininess": 22.0, "ao_strength": 0.9}}
    changed = cfg_mod.apply_display_config_migrations(user, from_version=3)

    assert user["metaball"]["shininess"] == 96.0
    assert user["metaball"]["ao_strength"] == 0.35
    assert set(changed) == {"metaball.shininess", "metaball.ao_strength"}


def test_a_value_the_user_chose_is_left_alone():
    """Anything that is not the old default was chosen, and stays chosen.

    A migration that overwrote choices would be worse than one that never ran:
    it would silently undo the settings someone came to rely on.
    """
    user = {"metaball": {"shininess": 40.0, "ao_strength": 0.9}}
    changed = cfg_mod.apply_display_config_migrations(user, from_version=0)

    assert user["metaball"]["shininess"] == 40.0, "a chosen value was overwritten"
    assert user["metaball"]["ao_strength"] == 0.35
    assert changed == ["metaball.ao_strength"]


def test_an_up_to_date_copy_is_not_touched():
    user = {"metaball": {"shininess": 22.0}}
    changed = cfg_mod.apply_display_config_migrations(
        user, from_version=cfg_mod.DISPLAY_CONFIG_VERSION
    )
    assert changed == []
    assert user["metaball"]["shininess"] == 22.0


def test_a_missing_section_or_key_is_not_invented():
    """Migration fixes stale values; it does not add settings."""
    user = {"cartoon": {"tube_radius": 0.5}}
    changed = cfg_mod.apply_display_config_migrations(user, from_version=0)
    assert changed == []
    assert "metaball" not in user


def test_a_stale_user_copy_is_migrated_on_load(tmp_path, monkeypatch):
    """End to end: the file on disk is updated and stamped, once.

    This is the case that mattered -- a copy written before the defaults changed
    -- and it is the one nothing checked, because the version comparison was
    never called from anywhere.
    """
    shipped = json.loads(
        cfg_mod.get_package_display_config_path().read_text(encoding="utf-8")
    )
    stale = json.loads(json.dumps(shipped))
    stale["_version"] = 3
    stale["metaball"]["shininess"] = 22.0
    stale["metaball"]["specular_strength"] = 0.12
    user_path = tmp_path / "chimol_display.json"
    user_path.write_text(json.dumps(stale), encoding="utf-8")

    # Patch what the loader actually consults. `_load_display_config` builds the
    # path from `_cs_settings.get_path`, not from `get_user_display_config_path`,
    # and patching the latter alone left the test reading the *shipped* file --
    # which now holds the new values, so it passed while proving nothing.
    class _Settings:
        @staticmethod
        def get_path(_what):
            return tmp_path

    monkeypatch.setattr(cfg_mod, "_cs_settings", _Settings)
    monkeypatch.delenv("CHIMOL_DISPLAY_CONFIG", raising=False)
    loaded = cfg_mod._load_display_config()

    assert loaded["metaball"]["shininess"] == 96.0
    assert loaded["metaball"]["specular_strength"] == 0.85

    written = json.loads(user_path.read_text(encoding="utf-8"))
    assert written["metaball"]["shininess"] == 96.0
    assert written["_version"] == cfg_mod.DISPLAY_CONFIG_VERSION


# --------------------------------------------------------------------------- #
# A default that changed twice inside one version
# --------------------------------------------------------------------------- #
def test_a_copy_stamped_with_the_current_version_can_still_be_corrected(shipped):
    """Someone who launched the app mid-change must not be stranded there.

    A default can change more than once before it settles, and anyone who ran
    the app in between has a file *already stamped with the current version*.
    Every later migration is then skipped for them -- the correction is
    unreachable and they keep a value nobody intended, which is exactly how a
    reported bug survived being fixed twice.

    A migration entry may therefore name several superseded values, and this
    holds that the intermediates named in the table really do arrive at what
    ships.
    """
    superseded: dict[tuple[str, str], list] = {}
    for version, sections in cfg_mod.DISPLAY_CONFIG_MIGRATIONS.items():
        for section, keys in sections.items():
            for key, (old, _new) in keys.items():
                values = old if isinstance(old, tuple) else (old,)
                superseded.setdefault((section, key), []).extend(values)

    for (section, key), olds in superseded.items():
        target = shipped.get(section, {}).get(key)
        for old in olds:
            stale = {section: {key: old}}
            cfg_mod.apply_display_config_migrations(stale, from_version=0)
            assert stale[section][key] == target, (
                f"{section}.{key}: a copy holding the superseded {old!r} "
                f"ended on {stale[section][key]!r}, not the shipped {target!r}"
            )


def test_a_value_the_user_chose_survives_a_multi_valued_migration():
    """Naming several old defaults must not turn into overwriting choices.

    The looser match is the risk of the mechanism: the more values a migration
    claims, the more likely one of them is something a person actually picked.
    Anything not named stays exactly as it is.
    """
    chosen = {"metaball": {"sigma_factor": 2.0, "iso_value": 0.30}}
    changed = cfg_mod.apply_display_config_migrations(chosen, from_version=0)

    assert chosen["metaball"] == {"sigma_factor": 2.0, "iso_value": 0.30}
    assert changed == []
