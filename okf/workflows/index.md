# Workflows

* [Change Tracking](change-tracking.md) - The mandatory loop for every material change: update the matching OKF concept + burn-down, append to the log, mark done, and commit (locally). Keeps changes traceable.
* [Environment & Build](build-and-env.md) - Pixi as the canonical environment/build manager, and building the compiled extensions.
* [IMP from source](imp-local-build.md) - Why `arm64` runs IMP built from `../imp` with `modules/bff` symlinked at `../imp.bff`, how one `.pth` wires the build tree into the env so rebuilds land with no re-install, and how imp-tricks was shadowing `IMP.bff.restraints` out of existence.
* [Testing](testing.md) - The test tasks (non-GUI, GUI, smoke, doctest) and how to run a single test.
* [Scheduled Maintenance Jobs](scheduled-jobs.md) - Durable macOS LaunchAgents that wake Claude Code headlessly to translate the UI, reconcile docs with the source, and advance the roadmap (`build_tools/jobs/`).
* [Reference checkouts](reference-checkouts.md) — `junk/` holds ~40 reference implementations; annotate what you have mined in the file itself (`CHISURF-REVIEWED` / `TAKEN` / `SKIPPED`), header only, and measure the coverage so "is this source exhausted?" has an answer.
