"""The Qt merger page reads a .cor chunk's count rate as the core reader does.

Its own copy of the reader split ``count_rate * duration`` over the two channels,
a factor 2000 short of the kHz per-channel convention: a folder of 20 kHz chunks
showed 0.01 kHz in the table and merged to 0.01 kHz.
"""

import numpy as np


def test_cor_chunks_keep_their_count_rate(qapp, qtbot, tmp_path):
    from chisurf.plugins.fcs.fcs_merger.wizard import ChisurfWizard

    folder = tmp_path / "chunks"
    folder.mkdir()
    for i in range(2):
        rows = [[1e-6, 2.0 + i, 10.0], [1e-5, 1.5, 20.0], [1e-4, 1.2, 0.0], [1e-3, 1.0, 0.0]]
        np.savetxt(folder / f"chnk-{i:04}.cor", rows, delimiter="\t")
    wizard = ChisurfWizard()
    qtbot.addWidget(wizard)
    page = wizard.page(wizard.pageIds()[0])
    page.lineEdit.setText(str(folder))
    page.open_correlation_folder(folder)
    table = page.tableWidget
    assert [table.item(0, c).text().strip() for c in (2, 3, 4)] == ["20.00", "20.00", "10.00"]
    assert page.mean_correlation["count_rate"] == 20.0
    page.save_mean_correlation()
    saved = np.loadtxt(page.target_filepath)
    assert saved[0, 2] == 20.0 and saved[1, 2] == 20.0
