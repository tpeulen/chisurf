# QuEst — Quenching Estimator

Structure-based simulation of dynamic PET quenching and FRET for dyes tethered
to proteins by flexible linkers. Peulen, Opanasyuk & Seidel, *J. Phys. Chem. B*
**2017**, 121, 8211 — https://doi.org/10.1021/acs.jpcb.7b03441

## This directory declares; the `quest` package implements

| path | what it is |
|---|---|
| `manifest.json` | Identity, entry points, and the RPC method table **copied from `quest/manifest.json`** |
| `api/contract.py` | Re-exports `quest.rpc.contract`. Defines nothing |
| `api/client.py` | Thin client over `quest.api` |
| `rpc/services.py` | Hands ChiSurf's dispatcher to `quest.rpc.services.register_services` |
| `cli/cli.py` | Delegates to `quest.cli:cli` |
| `gui/tool.py` | Embeds `quest.gui`'s AutoForm in a `ChisurfDockTool` |

There is no `core/`. QuEst is the core, and a second implementation of anything
here would be the drift `LAY-01` recorded when the CLI, the web backend and the
library each grew their own `simulate_site`.

## Two things that are load-bearing

**Nothing imports `quest` at module scope.** ChiSurf's discovery imports every
plugin at startup. The previous version of this plugin was a single
`__init__.py` doing `from quest.gui import TransientDecayGenerator` at the top,
so launching ChiSurf pulled in QuEst, IMP and numba whether or not anyone opened
the tool — and a broken QuEst install became a broken ChiSurf startup. Two tests
assert the import stays clean.

**The method table is copied, not restated.** If QuEst gains a method and
`manifest.json` here is not regenerated, `test_plugin.py` fails — rather than a
host discovering the gap at runtime.

## Regenerating the manifest

    python - <<'PY'
    import json, pathlib, quest
    src = json.loads((pathlib.Path(quest.__file__).parent / "manifest.json").read_text())
    dst_path = pathlib.Path("manifest.json")
    dst = json.loads(dst_path.read_text())
    dst["rpc_methods"] = src["rpc_methods"]
    dst["version"] = src["version"]
    dst_path.write_text(json.dumps(dst, indent=2, ensure_ascii=False) + "\n")
    PY

## Tests

    QT_QPA_PLATFORM=offscreen python -m pytest chisurf/plugins/quenching_estimator/test -q
