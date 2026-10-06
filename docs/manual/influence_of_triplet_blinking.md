---
type: Manual Page
title: Influence of triplet blinking
description: Be aware that significant amount of triplet blinking in the µs time range of the donor and / or acceptor fluorophore might mask the anticorrelation induced due to FRET in the FRET-CCF.
tags: [manual, fret, influence, triplet, blinking]
---

# Influence of triplet blinking

Be aware that significant amount of triplet blinking in the µs time range of the donor and / or acceptor fluorophore might mask the anticorrelation induced due to FRET in the FRET-CCF.

In the example shown below, 16 % of additional triplet blinking at 5.5 µs was added to the example of LF(*E* = 0.2) \<-> HF(*E* = 0.7).

Here, the FRET-CCF model has to be extended for a triplet-induced correlation term:

where *aT* and *tT* describe the amplitude and relaxation time of the triplet component.

```{image} _images/image_rId96.png
:align: center
```

One can see quite nicely in the FRET-CCF how the "dip" in the curve due to the anticorrelation term is counteracted by the triplet component.
