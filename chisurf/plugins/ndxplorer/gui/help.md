# ndXplorer

Explore a table of single-molecule bursts (or image pixels) as histograms of any two columns, gate populations and send the selection on.

## The window

| Part | What it does |
|---|---|
| Menu bar | Open and import data, save gates and burst ids, analyses (UMAP, Gaussian fits, projections). |
| Toolbar over the plot | Working folder, colour map, colour limits, **Contrast**, **Update**. |
| Plot controls | X, y and weighting column, bins, log scale, ranges, gates and clusters. |
| Map and margins | The 2-D histogram and the 1-D histograms of each axis; drag a rectangle to gate. |
| Parameters, Overlays, Equations | Constants, curves drawn over the map and derived columns. |

## Typical path

Open a table, pick the columns, press **Contrast**, gate a population on the map, then save the burst ids or send the selection to another ChiSurf tool.

## Further reading

- [ndXplorer guide](docs/guides/46_ndxplorer.md)
- [ndX bridges to ChiSurf](docs/guides/47_ndxplorer_bridges.md)
