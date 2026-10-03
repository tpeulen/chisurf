"""Capture historical Qt Browse with the same five-component native fixture.

The shared reference helper owns isolated historical source loading and strict
Qt-child validation. Only its in-memory post-construction hook is augmented;
no shared source or current GUI implementation is changed.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent / "renders" / "qt" / "spectra-browse-populated.json"


def child():
    helper = ROOT / "tools/emtk_migration/capture_qt_references.py"
    source = helper.read_text()
    hook = """
    if class_name == "SpectraTool":
        import numpy as np
        db = widget._db
        x = np.arange(400.0, 701.0, 5.0)
        for name, provenance, kind, center in (
            ("EGFP", "fpbase", "fluorescent_protein", 509),
            ("Alexa Fluor 488", "atto", "organic_dye", 519),
            ("ET525/50m", "chroma", "bandpass", 525),
            ("DMLP550", "thorlabs", "dichroic", 550),
            ("SPAD 650", "thorlabs", "apd", 650),
        ):
            db.register_component(name=name,source=provenance,kind=kind,
                properties={"em_max":center,"description":"Reference fixture"},
                spectra={"emission":(x,np.exp(-0.5*((x-center)/22.0)**2))})
        widget.nav_list.setCurrentRow(1)
        app.processEvents()
        browser=next(w for w in widget.findChildren(QWidget) if type(w).__name__ == "SpectraBrowserWidget")
        browser.refresh()
        browser._table.selectRow(0)
        app.processEvents()
"""
    source = source.replace(
        '    print("widget constructed", flush=True)',
        hook + '\n    print("widget constructed", flush=True)',
        1,
    )
    namespace = {"__file__": str(helper), "__name__": "_spectra_qt_reference"}
    exec(compile(source, str(helper), "exec"), namespace)
    namespace["child"]("chisurf.plugins.spectra_downloader.gui.tool:SpectraTool", OUT)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if "--child" in sys.argv:
        child()
        return
    with tempfile.TemporaryDirectory(prefix="spectra-qt-browse-") as scratch:
        env = dict(
            os.environ,
            QT_QPA_PLATFORM="offscreen",
            CHISURF_SETTINGS_DIR=scratch,
            MPLCONFIGDIR=scratch,
            MPLBACKEND="Agg",
            XDG_CACHE_HOME=scratch,
            CHISURF_QT_REFERENCE_ORDER="latest",
            CHISURF_QT_REFERENCE_WIDTH="1000",
            CHISURF_QT_REFERENCE_HEIGHT="700",
            CHISURF_QT_REFERENCE_TIMEOUT="50",
        )
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--child"],
            cwd=ROOT,
            env=env,
            timeout=55,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        print(OUT.with_suffix(".png"))


if __name__ == "__main__":
    main()
