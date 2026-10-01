# emtk port report — `traj_energy` (upgrade, audit-all row 36)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `traj_energy` / `chisurf/plugins/traj/traj_energy` — a second manifest over `chisurf/plugins/traj/potential_energy` |
| Port type | entrypoint only: the Qt widget and the emtk app are `traj_energy_calculator`'s, brought to parity in EMTK-1 (`okf/plugins/emtk-ports/traj_energy_calculator/REPORT.md`) |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | one commit "traj_energy: emtk entrypoint for the calculator's app" (code, tests, evidence) |
| Board | `T-20261002-EMTK1C` |

## 1. State at start

Modified `manifest.json` (emtk entrypoint = the calculator's `make_app`) and `__init__.py` (a lazy `__getattr__` export of the
Qt widget). The eager `from …widget import PotentialEnergyWidget` was left above it, so importing the package still loaded
PyQt5 — caught by the new test, removed.

## 2. Parity

Same app, same widget: the parity, science and breakage evidence is the calculator's. Here: the manifest declares the
calculator's emtk and Qt entrypoints; importing the package loads no Qt and the widget only on request; the port is Qt-free.

## 4. Automated evidence

```
before: 15 controls; after: 23 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/traj_energy
compare: exit=0   (lost ca / cutoff / h, explained as in the calculator's deliberate.json)
```

## 6. Tests

```
$ python -m pytest chisurf/plugins/traj/traj_energy -q -p no:cacheprovider
3 passed
```

Breakage: the stream's own state (eager import kept) failed the Qt-free import test; fixed.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 (the calculator's draws) · [x] D5 · [x] D6 · [x] D7 (the calculator's guide/help) · [x] D8 · [x] D9 · [x] D10
