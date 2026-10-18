# Qt reference captures (retired)

The Qt window is gone, so the capture script (`capture_qt_references.py`) is retired: it
loaded the original Qt implementations from the repository history and cannot run without
Qt. What it recorded stays in `okf/plugins/emtk-references/`: PNGs, per-plugin JSON with
source revision, window size and control/tooltip inventory, and a capture index. They are
the frozen before-halves of the emtk ports. Failures and timeouts have JSON diagnostics;
no failed capture proves parity. Captures show initial empty/default state, so
workflow/data-dependent states needed separate parity checks.

`summarize_qt_references.py` still merges the recorded results into the canonical
directory and regenerates the manifest catalog, summary and categorized blocker report.
It excludes CLI/backend-only plugins from screenshot requirements only by their lack of a
GUI/script entrypoint; they stay in the catalog. Host actions such as Menu Switch and
Screenshot have no standalone tool window; their capture record stays unresolved.
