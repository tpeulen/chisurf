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
they point **at the master**. **Connect base** adds dashed lines between the
owners themselves — every fit *and* every plugin group — which is how a
plugin's working model is shown sitting with the fits it can be linked to
rather than off on its own.

## Doing things

- **Link two parameters** — drag one parameter node onto another. The one you
  dragged becomes the follower. Or click both (the first gets a red rim: it is
  the master) and press 🔗 **Link**.
- **Break a link** — double-click the arrow, or select the follower and press
  🧹 **Unlink**. Tick **all** to unlink every parameter in every fit.
- **Move things** — drag a fit to move it with all its parameters; hold
  <kbd>Shift</kbd> to move a single parameter node. Drag the background to pan,
  wheel to zoom, ⌖ to fit the network back into the panel.
- **Edit a parameter** — click its node; its editor appears in **Selection**.
- **Everything at once** — the **Parameters** panel is a table of every
  parameter in every fit and every registered group, searchable, with value,
  bounds, fixed state and link.

A link that would make a cycle (A follows B follows A) is refused, with the
parameters named.

## Staying in step with the fits

**⟳ Refresh** rebuilds the network from the current fits and lays it out again;
use it whenever the picture and the fits disagree.

With **auto** ticked (the default) that happens by itself when a fit or a link
changes — cheaply. Change events are coalesced into one wake-up, and the layout
only re-runs when the network's *shape* changed: a parameter appearing,
disappearing, or becoming fixed / linked / free. A fit running for a thousand
iterations changes values, not shape, so it costs nothing here. Untick **auto**
to refresh only by hand; the status bar then says when the picture has gone
stale.

## Layouts

The layout algorithm only decides where nodes go; it never changes the fit.
`kamada_kawai` and `spring` pull linked parameters together, which makes shared
parameters visible at a glance; `shell` and `spectral` expose structure in a
large network. **Spread** grows the network past the panel edges when it is too
crowded to read — pan and zoom to explore it.

## Saving

💾 saves the network as GraphML (`.gml`) — node values, fixed flags and links.
Loading one applies all three back onto the current fits, which is how a linking
scheme is reused on a new set of datasets.

## Further reading

- [Global analysis — what linking does to the estimate](docs/concepts/global_analysis.md)
- [Global analysis: linking parameters across fits](docs/guides/60_global_analysis.md)
- [Parameter uncertainty](docs/concepts/parameter_uncertainty.md)
