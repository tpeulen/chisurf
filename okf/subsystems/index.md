# Subsystems

* [Core](core.md) - Domain objects, fitting, data, models, math, settings, actions, and the API facade.
* [Data model](data-model.md) - `Base`/`Data`/`DataCurve`, data groups, experiment readers, and dataset flow.
* [Data IO](data-io.md) - File loading, TTTR/photon readers, format registry, and slow-storage staging.
* [Burst companion files](burst-companions.md) - The one contract every burst-analysis plugin follows when writing results beside the bursts, so a folder merges into one table without misaligning.
* [Fluorescence domain](fluorescence-domain.md) - Shared fluorescence math and algorithms used by models and plugins.
* [Fitting engine](fitting.md) - Fit/FitGroup, weighted residuals, global analysis, error analysis, and sampling.
* [Hidden Markov models](hidden-markov-models.md) - The in-tree Gaussian HMM (fused compiled E-step, data-driven initialisation, SQUAREM acceleration) and the shared analysis seam every state-reporting tool calls.
* [Fitting models](models.md) - TCSPC/FCS/PDA/PCH/DEER/RICS/structure models and data-described editors.
* [MLE lifetime fitting (fit2x)](mle-lifetime-fitting.md) - The tttrlib Fit23/24/25/26 Poisson-MLE engine and the dt/period/background/gamma input contract shared by burst and imaging fits.
* [Parameters](parameters.md) - Scalar parameters, bounds, links, dependency graph, and fit degrees of freedom.
* [Graph layer (chinet.graph)](graph.md) - In-tree graph containers, algorithms, layouts and GraphML I/O shared by the factor graph, the node editor and the global-parameter view.
* [GUI & AutoForm](gui-autoform.md) - The Qt application and the data-driven AutoForm UI framework.
* [Plotting (chiplot)](chiplot.md) - The single renderer-neutral 2-D plotting API every call site draws through, its backend contract, and the guard that keeps the rendering library behind it.
* [Tables (chitable)](gui-tables.md) - The shared model/view table family: sources, vectorised filtering, value colouring, column hiding and export.
* [Toolbar action vocabulary](gui-action-vocabulary.md) - One icon, colour, tooltip and position per semantic action, including the run/restart/pause/stop transport controls.
* [Internationalisation](i18n.md) - The Qt-free translation seam, QTranslator bootstrap, string-extraction kit, and view.json/manifest/.ui localization.
* [Operation history](history.md) - Append-only action history, headless replay, and MMFDB event-log projection.
* [Macros, CLI & scripting](macros-cli.md) - Macros, `csc`, GUI scripts, and the recording QtConsole.
* [LLM agent](llm-agent.md) - The plain-language assistant: described, safety-tiered tools, the observe-act loop, and its head-less CLI.
* [Project persistence](project-persistence.md) - `.csp` archive format, UID-keyed project state, and UI-state capture.
* [Regions of interest](roi.md) - One ROI geometry for gating and imaging alike: point membership plus pixel rasterisation, boolean composition, JSON persistence, and the segmentation bridge.
* [Pipelines](pipeline.md) - Typed DAGs of transformer invocations persisted and replayed through MMFDB provenance.
* [Compiled Modules](compiled-modules.md) - The C++ extensions in `modules/` that must be built before tests.
