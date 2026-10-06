---
type: Manual Page
title: Correlation merging
description: Finally, the computed correlation curves can be merged (Fig.30).
tags: [manual, correlation, merging]
---

# Correlation merging

Finally, the computed correlation curves can be merged (**Fig.30**). Before merging the correlation curves of the subsets into a joint correlation curve outliers (e.g. caused by aggregates) can be removed.

```{image} figures/fcs_merger_step.png
:align: center
```

**Fig.30 Selecting and merging correlation curves** (step *5. FCS Merger* of the
FCS hub, on the six subsets of Fig.29). The table lists every subset's curve
with the count rate of both correlation channels (**CR A**, **CR B**) and its
**Duration**; **Use** decides whether it enters the merge. The curves are drawn
top right, their merge (*Merge of 6*) below it.

Untick **Use** -- or double-click a row -- to leave a subset out (an aggregate,
a bleaching event); **Delete** removes it from the list. The merge is written
to **Target** (by default the `cr5` folder's name, as a Seidel Kristine `.cor`
file) with **💾 Save**; **🚀 Add to ChiSurf** saves it and loads it as an FCS
dataset for fitting. **📂 Open folder…** merges any folder of correlation
curves, not only the ones this pipeline just computed.
