"""A TCSPC text decay is named after its file, not its path (found 2026-10-11, lifetime guide).

The full path filled the Datasets list, every fit title ("Lifetime - /Users/.../Decay_577D.txt")
and the emtk shell's dataset rows.
"""

from pathlib import Path

from chisurf.core.experiments.tcspc.reader import TCSPCReader

DECAY = Path(__file__).resolve().parents[1] / "data" / "tcspc" / "ibh_sample" / "Decay_577D.txt"


def test_the_curve_and_its_group_carry_the_file_name():
    reader = TCSPCReader(record_provenance=False)
    reader.skiprows, reader.dt = 9, 0.0141
    group = reader.read(str(DECAY))
    assert [curve.name for curve in group] == ["Decay_577D.txt"]
    assert group.name == "Decay_577D.txt"
    assert group[0].filename == str(DECAY), "the path is still recorded"
