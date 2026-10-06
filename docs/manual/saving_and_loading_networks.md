---
type: Manual Page
title: Saving and loading networks
description: By default, the Global view plugin displays all models / fits in the current ChiSurf instance.
tags: [manual, fitting, global-analysis, plugins]
---

# Saving and loading networks

The Global View displays all fits of the current ChiSurf session. **Save…** in its toolbar writes the network -- every parameter with its value and fixed flag, and the links -- to a GraphML file (**Fig.34**, the window in Fig.32). The file starts like this:

```xml
<?xml version='1.0' encoding='utf-8'?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="d0" for="node" attr.name="node.idx" attr.type="long" />
  <key id="d1" for="node" attr.name="node.type" attr.type="string" />
  <key id="d2" for="node" attr.name="node.name" attr.type="string" />
  <key id="d3" for="node" attr.name="fit.idx" attr.type="long" />
  <key id="d4" for="node" attr.name="fixed" attr.type="boolean" />
  <key id="d5" for="node" attr.name="name" attr.type="string" />
  <key id="d6" for="node" attr.name="param.uid" attr.type="string" />
  <key id="d7" for="node" attr.name="owner.uid" attr.type="string" />
  <key id="d8" for="node" attr.name="owner.id" attr.type="string" />
  <key id="d9" for="node" attr.name="value" attr.type="double" />
  <graph edgedefault="undirected">
    <node id="0">
```

**Fig.34.** The beginning of a saved network: one node per fit and per parameter, with the attributes listed in the `key` elements.

**Load…** applies a saved network to the running session: parameter values, fixed flags and links. A parameter is matched by its unique identifier, or -- for a file from another session -- by the position of its fit and its name, so the fits must then be open in the same order as when the file was saved (**Fig.35**).

```{image} figures/globalview_before_load.png
:align: center
```

```{image} figures/globalview_after_load.png
:align: center
```

**Fig.35.** The two IBH sample fits of [Fig.1](overview.md) after their link was removed (top, "0 linked") and after **Load…** of the network saved before (bottom): the lifetime `t0` of the second fit follows the first again ("1 linked").
