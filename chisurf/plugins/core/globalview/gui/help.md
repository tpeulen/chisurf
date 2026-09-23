# Global View — the parameter network

Global View draws every open fit, every parameter in it, and every **link**
between parameters. A link makes one parameter *follow* another: the follower is
no longer estimated, it takes the master's value. That is what makes a fit
global — two datasets sharing one lifetime are two fits whose `tau` parameters
are linked.

## Reading the network

| Node | Meaning |
| --- | --- |
| **fit** (blue, large) | one dataset being fitted |
| **plugin group** (orange, large) | a registered out-of-fit parameter group — a plugin's working model |
| **free parameter** (purple) | estimated by the fit |
| **linked parameter** (green) | follows another parameter |
| **fixed parameter** (grey) | held at its value; shown only with **Include fixed** |

Thin grey lines are *ownership*: they join a parameter to the fit or group it
belongs to, and mean nothing else. The bright cyan arrows are the links, and
they point **at the master**. **Connect base** adds dim lines between the
owners themselves — every fit *and* every plugin group — which is how a
plugin's working model is shown sitting with the fits it can be linked to
rather than off on its own.

## The factor graph

**Show ▸ Factor graph** draws the same fits as the posterior a global fit
estimates. Each dataset is a **square**: its likelihood. It is joined to the
**variables** it depends on, *links resolved*: a follower is no variable of
its own, since its value is its master's, so a lifetime two datasets share is
**one** variable joined to both squares, drawn gold (*shared*). The follower
hangs off it by its link arrow, and a held parameter, shown with **Include
fixed**, is *evidence* on the square that reads it.

| Node | Meaning |
| --- | --- |
| **likelihood** (blue square) | one dataset: the data and the model that predicts it |
| **shared variable** (gold) | read by two or more likelihoods: what makes the fit global |
| **variable** (purple) | read by one likelihood only |
| **linked parameter** (green) | a follower, beside the variable it takes its value from |
| **fixed parameter** (grey) | evidence: held, read by one likelihood |

The status line counts the likelihoods, the variables, the shared ones by name,
and the **independent blocks**. Two blocks mean two groups of datasets with no
variable in common: however many links were drawn, they are two separate fits
that happen to share a window.

## Doing things

- **Link two parameters** — drag from one parameter onto another. The one you
  dragged from becomes the follower, and the arrow you drew is the arrow that
  stays: it points at the master. Or click both (the first is the master) and
  press **Link**.
- **Break a link** — break the arrow in the network, or select the follower and
  press **Unlink**. Tick **all** to unlink every parameter in every fit.
- **Move things** — drag a node to move it. Drag the background with the middle
  button to pan, wheel to zoom, **Fit view** to fit the graph back into the panel.
- **Edit a parameter** — click its node; it appears in **Selection** with the fit
  it belongs to and its role. Double-click a value to type a new one; a
  follower's value is its master's and does not open, and a bound opens only
  while **Bounds** is ticked.
- **Everything at once** — the **Parameters** panel is a table of every
  parameter in every fit and every registered group, filterable, with value,
  bounds, fixed state and the row it follows. Type a row number into
  **Link row** to link, clear it to unlink. Right-click the header to pick the
  columns, **Shade values** to colour values by size, **Export…** to write the
  table to CSV. Clicking a row selects its node.
- **Arrange the panels** — every panel is a dock: drag its tab to float it, drop
  it onto another region to dock it there. The arrangement is remembered.

A link that would make a cycle (A follows B follows A) is refused, with the
parameters named.

## Staying in step with the fits

**Refresh** rebuilds the network from the current fits and lays it out again;
use it whenever the picture and the fits disagree.

With **auto** ticked (the default) that happens by itself when a fit or a link
changes — cheaply. Change events are coalesced into one wake-up, and the layout
only re-runs when the network's *shape* changed: a parameter appearing,
disappearing, or becoming fixed / linked / free. A fit running for a thousand
iterations changes values, not shape, so it costs nothing here. Untick **auto**
to refresh only by hand; the status line then says when the picture has gone
stale.

## Layouts

The layout algorithm only decides where nodes go; it never changes the fit.
`kamada_kawai` and `spring` pull linked parameters together, which makes shared
parameters visible at a glance; `shell` and `spectral` expose structure in a
large network. **Spread** grows the network past the panel edges when it is too
crowded to read — pan and zoom to explore it.

## Saving

**Save…** writes the network as GraphML (`.gml`) — node values, fixed flags and links.
**Load…** applies all three back onto the current fits, which is how a linking
scheme is reused on a new set of datasets.

## Further reading

- [Global analysis — what linking does to the estimate](docs/concepts/global_analysis.md)
- [Global analysis: linking parameters across fits](docs/guides/60_global_analysis.md)
- [Parameter uncertainty](docs/concepts/parameter_uncertainty.md)
