# Qt reference captures

Run from the ChiSurf checkout with its existing GUI environment:

```sh
pixi run -e test python build_tools/dev_utils/emtk_migration/capture_qt_references.py --timeout 25
```

By default every manifest is catalogued, excluding test/template directories.
Use `--groups calculator core burst` or `--plugins fret_calculator kappa2_dist`
to narrow the selection, and `--jobs 1` to serialize (default: three). Each plugin launches in a separate process with a
bounded timeout and disposable settings. Historical revisions that predate the
settings-directory environment variable also have `Path.home()` isolated.

The script uses the earliest genuine Qt implementation in git history, taking
a snapshot of its Python/UI/configuration resources. This keeps the original
shared Qt renderers instead of accidentally using today's EMTK adapters. Bundled
third-party modules still come from the current installed checkout/environment.
The untracked PDA companion is supplemented from the checkout when necessary;
successful metadata explicitly records that supplement.
MMFDB admin and user-editor references inject the original real in-process
client against a disposable database and authenticated temporary account; no
auth or service handlers are mocked. Switch User captures its original LoginDialog.
External factories resolve their own bundled repository history (for example Chimol).
Historical flat plugin asset paths are aliased to the exact historical category
directory to repair early move-related `.ui` lookup failures; aliases are recorded.
Split/Convert, code editor, and help use their explicit historical Qt factories.
Use `--prefer-latest` for the latest native Qt implementation before the port.
Use `--tab-pages` to capture every original Qt tab page as well as initial state.
References select the supported pyqtgraph backend with OpenGL disabled, so
historical Qt control panels cannot silently use the EMTK plot renderer.
Original tool construction and all child widgets still pass the native Qt check.
Uniform blank framebuffers are rejected even when a Qt grab technically succeeds.

Results go to `okf/plugins/emtk-references/`: PNGs, per-plugin JSON containing
source revision, window size and control/tooltip inventory, and a capture index.
Failures and timeouts have JSON diagnostics. A QWidget that contains EMTK child
widgets is rejected instead of labelled as a Qt reference. Captures show initial
empty/default state; workflow/data-dependent states still need separate parity
checks. Offscreen captures cannot validate native window chrome.

The script exits nonzero if any plugin fails. No failed capture proves parity or
functionality. Review successful PNGs before using them as visual references.

After separate retry batches, run `summarize_qt_references.py` to merge successes
into the canonical directory and regenerate the manifest catalog, summary, and
categorized blocker report. It excludes CLI/backend-only plugins from screenshot
requirements only by their lack of a GUI/script entrypoint; they stay in the catalog.
Host actions such as Menu Switch and Screenshot have no standalone tool window;
their capture record stays unresolved and their behavior needs the main app host.
