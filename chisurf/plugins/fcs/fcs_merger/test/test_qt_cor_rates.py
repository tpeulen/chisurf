"""The Qt merger page reads a .cor chunk's count rate as the core reader does.

Its own copy of the reader split ``count_rate * duration`` over the two channels,
a factor 2000 short of the kHz per-channel convention: a folder of 20 kHz chunks
showed 0.01 kHz in the table and merged to 0.01 kHz.
"""

import numpy as np


def test_cor_chunks_keep_their_count_rate(qapp, qtbot, tmp_path):
    from chisurf.plugins.fcs.fcs_merger.gui.app import create_app

    folder = tmp_path / "chunks"
    folder.mkdir()
    for i in range(2):
        rows = [[1e-6, 2.0 + i, 10.0], [1e-5, 1.5, 20.0], [1e-4, 1.2, 0.0], [1e-3, 1.0, 0.0]]
        np.savetxt(folder / f"chnk-{i:04}.cor", rows, delimiter="\t")
    app = create_app()
    app.load_folder(folder)
    app.job.future.result(timeout=5)
    app.job.poll()
    page = app.model
    rows = page.curve_rows()
    assert [rows[0][key] for key in ("cr_a", "cr_b", "duration")] == [20.0, 20.0, 10.0]
    assert page.mean_correlation["count_rate"] == 20.0
    from chisurf.core.fluorescence.fcs.merge import save_mean_correlation

    save_mean_correlation(page.mean_correlation, page.output)
    saved = np.loadtxt(page.output)
    assert saved[0, 2] == 20.0 and saved[1, 2] == 20.0

    app.close()
