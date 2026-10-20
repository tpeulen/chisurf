"""A photon file opened in one test module is not resident in the next."""

from __future__ import annotations

from pathlib import Path

import pytest

HT3 = Path(__file__).resolve().parent / "data/clsm/PQ_Olympus_MFIS.ht3"


@pytest.mark.skipif(not HT3.exists(), reason="CLSM test data not present")
def test_release_empties_the_shared_reader_cache():
    from chisurf.core.fio import staging
    from test.process_caches import release_process_caches

    staging.open_tttr(str(HT3))
    assert staging.tttr_cache_stats()["entries"] >= 1
    release_process_caches()
    assert staging.tttr_cache_stats() == {"entries": 0, "bytes": 0}
