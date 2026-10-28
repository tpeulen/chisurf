"""The measurement profiles shipped with the Record tool (``acq/profiles/*.json``).

Each is an ordinary acquisition settings file, made from the SymPhoTime profiles on the
MT200 (Standard, PIE, CY PIE); the Record tool lists them next to the workspace's settings.
"""

from __future__ import annotations

from chisurf.plugins.core.acq.live import settings_file


def test_every_shipped_profile_loads_and_validates():
    profiles = settings_file.shipped_profiles()
    names = [name for _path, name in profiles]
    assert len(profiles) >= 3
    assert any("Standard" in n for n in names) and any("PIE" in n for n in names)
    for path, _name in profiles:
        doc = settings_file.load(path)
        assert settings_file.validate(doc) == []


def test_the_mt200_profiles_carry_symphotime_s_tcspc_settings():
    by_name = {name: settings_file.load(path) for path, name in settings_file.shipped_profiles()}
    std = next(d for n, d in by_name.items() if "Standard" in n)
    pie = next(d for n, d in by_name.items() if n.startswith("MT200 PIE"))
    flat = settings_file.device_settings(std["device"])
    assert flat["sync_level_mv"] == 350 and flat["sync_offset_ps"] == 5000
    assert flat["input_offset_ps[0]"] == 130 and flat["input_offset_ps[2]"] == -40
    assert flat["binning"] == 5                                   # 32 ps
    # one TCSPC setting for every MT200 profile; they differ in the lasers and the run
    assert all(d["device"] == std["device"] for d in by_name.values() if d["name"].startswith("MT200"))
    assert pie["experiment"]["preset"] == "pie" and std["experiment"]["preset"] == "single_color"
    # runs are open-ended: no profile sets a duration
    assert all("duration_s" not in (d.get("run") or {}) for d in by_name.values())
    # the SOM-D is not driven yet: no profile asks the laser backend for an oscillator
    assert all("oscillator" not in (d.get("laser") or {}) for d in by_name.values())


def test_the_record_panel_lists_and_loads_a_profile(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel

    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    rows = dict(model.settings_options())
    key = next(k for k, label in rows.items() if k.startswith("profile:") and "Standard" in label)
    model.settings_address = key
    assert model.enabled("load_settings")
    assert model.load_settings()
    assert model.device_values.get("sync_level_mv") == 350
