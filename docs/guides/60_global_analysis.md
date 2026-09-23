---
type: Guide
title: 'Global analysis: linking parameters across fits'
description: 'Theory: Global analysis · Tool: Main ▸ Tools ▸ 🌐 Global View · Code: chisurf.core.fitting.fit, chisurf.core.models.global_model'
tags: [guides, fitting, global-analysis]
---

# Global analysis: linking parameters across fits

**Theory:** [Global analysis](../concepts/global_analysis.md) ·
**Tool:** Main ▸ Tools ▸ 🌐 Global View ·
**Code:** `chisurf.core.fitting.fit`, `chisurf.core.models.global_model`

This tutorial ties two measurements together through a shared parameter: first
in the GUI, using the parameter network; then headless, in a dozen lines of
Python. The worked example is deliberately small — one lifetime shared between
two decays — so that every number below can be checked by eye.

## 1. Fit each dataset on its own first

Global analysis constrains models; it does not repair them. If one member does
not describe its own data, linking only spreads that failure across the series.
So load the datasets, add a fit for each, and run them separately before doing
anything here.

## 2. Open the parameter network

**Main ▸ Tools ▸ 🌐 Global View** draws every open fit, every parameter in it,
and every link between parameters.

- a large **blue** disc is a fit; a large **orange** one is a plugin's
  parameter group
- small discs are its parameters: **purple** free, **green** following another
  parameter, **grey** fixed (shown only with **Include fixed** ticked)
- thin grey lines are ownership — which parameter belongs to which fit
- **cyan arrows are the links**, and they point *at the master*
- dim lines appear with **Connect base**: they join the owners themselves,
  fits and plugin groups alike, so a plugin's working model (an ndX selection,
  a calculator) is visibly part of the same web rather than off on its own

The colour key sits in the top-left corner of the panel, and the status line
counts what is on screen. Every panel (Network, Parameters, Selection, View) is
a dock: drag its tab to float it or to dock it elsewhere, and the arrangement is
remembered.

```{figure} figures/globalview_network.png
:name: fig-globalview-network
:width: 100%

Three fits sharing one donor lifetime, *FRET-low* a fit group of two curves,
so four owners. Each **blue** disc is a fit (or one local fit of a group)
surrounded by its parameters; the two **cyan arrows** run from the followers'
`t0` to the master's, and they point *at* the master, so the direction of the
constraint is readable off the picture. The follower nodes are **green** and the
master stays **purple**. The owner in the top-left corner has no arrow at all:
the second curve of *FRET-low*, which the link was never made for.
```

## 3. Link the shared parameter

Two ways, and they do the same thing:

- **Drag** from one parameter onto another. The one you dragged from becomes
  the follower, and the arrow you drew is the one that stays: it points at the
  master.
- **Click** the master, click the follower, then press **Link** on the toolbar.

The follower turns green and an arrow appears. In **Selection** its role reads
*follower* and its value no longer opens for typing: it takes the master's. A
link that would create a cycle is refused by name.

To undo one, break its arrow, or select the follower and press **Unlink**.
Ticking **all** first clears every link in every fit.

```{note}
Two fits of the same model name their parameters identically, so `tau1` on its
own does not say which fit is being edited. The **Selection** table lists
each selected parameter with the fit it belongs to, and the **Parameters** table
has an *Owner* column — use them before believing which node you clicked.
```

If the network is too crowded to work in, change **Layout** in the **View**
panel, raise **Spread**, use the wheel to zoom and drag the background with the
middle button to pan. **Fit view** puts everything back in the panel.

The network follows the session on its own: it redraws when a fit or a link
changes, and only re-runs the layout when the *shape* changed, so a fit running
for a thousand iterations costs nothing. **Refresh** forces a redraw, and
unticking **auto** hands that over to you entirely — the status line then says
when the picture has gone stale.

## 4. Check that the link took effect

Open the **Parameters** panel: it is the same information as a table — every
parameter of every fit and every registered plugin group, filterable, with
value, bounds, fixed state, and a **Link row** column naming the row each
follower follows (type a row number there to link, clear it to unlink). A
follower's row is dimmed. Right-click the header to choose columns;
**Export…** writes the table to CSV.

**Show ▸ Factor graph** in the **View** panel is the check that the link
couples what you meant it to. Each dataset becomes a square — its likelihood —
joined to the variables it depends on, links resolved: the shared lifetime is
**one gold variable** joined to every square that reads it, and each follower
hangs off it. The status line names the shared variables and counts the
**independent blocks**; more than one block means some datasets share nothing
with the rest, whatever the network looked like.

```{figure} figures/globalview_factor_graph.png
:name: fig-globalview-factor-graph
:width: 100%

The same session as a factor graph. Three likelihoods (squares) read the one
shared `t0` (gold); the fourth -- the second curve of *FRET-low* -- reads a
`t0` of its own, and the status line says so: *1 shared (t0) · 2 independent
blocks*. Linking that curve's `t0` too makes it one block.
```

The number that matters is the **free-parameter count**, which must drop. If it
did not, the link is not in effect and any result is meaningless.

## 5. Run the fits again

A link changes the objective of every fit it touches, so results computed before
it are stale. Re-run each fit. Expect $\chi^2_r$ to rise a little for the
individual datasets — that is the price of the constraint. A large rise means
the parameter is not actually shared; see
[the concept page](../concepts/global_analysis.md) for how to test that.

## 6. Save the scheme

**Save…** writes the network as GraphML (`.gml`): node values, fixed flags and
links. **Load…** applies a saved one back onto the fits you have open, which is how the same
linking scheme is reused on a new set of datasets.

## Headless: linking two fits

Everything above is available without the GUI. Two decays share a lifetime and
differ in amplitude:

```python
import numpy as np
import chisurf.core.data
import chisurf.core.fitting.fit as fit_mod
import chisurf.core.models.parse

rng = np.random.default_rng(0)
x = np.linspace(0.0, 4.0, 128)
TRUE_TAU, AMPS = 2.5, (1.0, 0.35)      # tau is shared, a is not

fits = []
for amp in AMPS:
    y = amp * np.exp(-x / TRUE_TAU) + rng.normal(0.0, 0.01, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, 0.01))
    fit = fit_mod.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'a*exp(-x/tau)'
    fit.model.find_parameters()
    fit.run()
    fits.append(fit)

for k, f in enumerate(fits):
    print(k, f.model.parameters_all_dict['tau'].value, f.chi2r)
```

```text
0 2.5085956876064945 0.9301236777296892
1 2.4834977809457968 1.1647084389660811
```

Two independent answers for one quantity. Link the second fit's `tau` to the
first's:

```python
fits[1].link_parameter('tau', 'tau', fits[0])   # target name, source name, source fit
print(len(fits[1].model.parameters))            # free parameters: 2 -> 1
```

`fit.unlink_parameter('tau')` reverses it, and
`chisurf.core.parameter.Parameter.check_recursive_link` is what refuses a cycle.

## Headless: the joint fit

Linking makes the follower *track* the master. To have the shared value
estimated from **both** datasets at once — the actual global estimator — put the
member fits under a `GlobalFitModel`, whose residual vector is their residuals
end to end:

```python
from chisurf.core.models.global_model.globalfit import GlobalFitModel

host = fit_mod.Fit(model_class=GlobalFitModel, data=fits[0].data)
host.model.fits = fits
host.model.find_parameters()
host.run()

tau = fits[0].model.parameters_all_dict['tau']
print(float(tau.value), host.chi2r)
```

```text
2.505863211955553 1.0413524086960884
```

One lifetime, both decays, one number out — and the follower in `fits[1]`
reports the same value with `is_linked` true. The distinction matters: running
the member fits individually after linking constrains them, but only the host
minimises the *joint* objective and only its covariance reflects all the data.

## Doing it from the assistant

The [AI assistant](40_ai_assistant.md) has a `global-fitting` skill covering the
same ground: "link tau1 in all the fits to the first one" resolves to
`link_parameters`, and `list_links` reports the linking scheme and the
free-parameter count per fit. It will remind you to re-run the fits.

## See also

- [Global analysis (theory)](../concepts/global_analysis.md)
- [Parameter uncertainty](39_parameter_uncertainty.md) — what a shared
  parameter's interval means
- [Lifetime and anisotropy fitting](10_lifetime_anisotropy_fitting.md) — the
  most common thing to fit globally
- Tool: **Global View** (`chisurf/plugins/core/globalview/`).
