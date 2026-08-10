# Spot Finder

Finds the objects in an image — molecules, beads, cells — and writes them, with
their pixels, into the measurement's own container. It fits nothing: the
lifetimes come from **Region MLE**, which fits the regions found here.

## Why detection is its own tool

A fit that finds its own regions cannot be shown what it is about to fit. The
tool this one was split out of had a *preview* that returned exactly the labels
the fit would use — and the fit ignored them and segmented a second time. The
two agreed only for as long as every setting reached both paths.

Separating them buys three things a combined tool cannot have: a segmentation
you can look at and correct before committing to a fit, one that can be
**re-used** (two analyses of the same field fit the same objects), and a fit
that can be handed regions from *any* detector, including one drawn by hand.

## The detectors

| method | what it does | when |
|---|---|---|
| `watershed` | smooth, threshold, split objects that touch by a distance transform | objects that touch — the default |
| `threshold` | connected components of the thresholded image, no splitting | well-separated objects; a watershed can only ever *over*-split a lone spot |
| `log` | Laplacian-of-Gaussian scale space | spots of unknown width — it reports each spot's own σ |
| `dog` | difference-of-Gaussians; the cheaper approximation of `log` | as above, faster, slightly less accurate about the width |

`log` and `dog` answer *where and how wide*, and the file needs *which pixels*,
so each spot becomes a disc of radius `√2·σ` — the width the detector measured,
not one chosen in advance. Overlapping discs are arbitrated by distance, so a
contested pixel goes to the nearer centre and no photon is counted twice.

## Workflows

A detection is a recipe, and a recipe worth re-running is worth writing down.
The **Workflow** selector loads one wholesale — picking it replaces every
setting, because keeping the previous recipe's threshold is how a workflow
becomes decorative.

Shipped: **single_molecule** (the standard one, and the pipeline the lifetime
fit has always been run on), **camera_spots** (a LoG scale space, `min_area` 2
to reject hot pixels), **objects** (connected components, no splitting).

The same recipes drive the headless CLI:

```
spot-finder workflows                       # what is shipped
spot-finder detect FILE …                   # the standard workflow
spot-finder detect --workflow camera_spots FILE …
spot-finder run recipe.json FILE …          # a recipe of your own
spot-finder detect --save-workflow mine.json FILE …
```

An option you do not type does not override the workflow; an unknown setting in
a document is **refused**, never ignored, because a misspelled key that runs at
the default records a parameter that never took effect.

## Picking by hand

A threshold finds every object or none. Click the image on the **Regions** tab
and a 2-D Gaussian is fitted to what is under the cursor: the click seeds it and
the fit decides, so a click two pixels off still lands on the object, and the
region gets the width the fit measured. A fit that does not converge is refused
with a reason rather than leaving an ellipse where nothing was found. **Add
picks** makes them part of the detection — only where nothing was found already,
since a pick is an object the detector missed, not a second claim on one it got.

## What gets written

Each detection is a **pair** in the measurement's container: an `image_data`
label raster and a `region_table` measuring it, joined by the `label` column.
Both are needed — a table of centroids and areas is readable and cannot be
fitted, because a fit reaches a region's photons through its *pixels*.

One row per region, always, including regions a later analysis skips. Name the
detection and two attempts on one field can be compared instead of replacing
each other.

## Batch

Every input gets a row in the **Run** tab — `ok`, `empty`, `failed` or
`skipped` — with the reason beside it. A file that found nothing says so and
never quietly leaves the list: a batch reporting ninety of a hundred files looks
exactly like a batch of ninety.

## Try it without your own data

**🧪 Load demo** simulates a field with four objects of known lifetimes (1.0,
3.6, 2.2 and 0.6 ns) on two detectors, with the IRF measurement that belongs to
it. Real photons, written as an ordinary PTU, so nothing about the workflow is a
special case — and the answer is known, so a detection can be checked rather
than trusted.

## Further reading

- [Region properties](docs/concepts/region_properties.md)
- [Regions and gating](docs/guides/48_regions.md)
