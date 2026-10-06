---
type: Manual Page
title: Linking parameters
description: Parameters can be selected by clicking on the respective nodes.
tags: [manual, linking, parameters]
---

# Linking parameters

A linked parameter *follows* another one: it is no longer estimated and takes
the other parameter's value. Links are made in two places. In a fit's
parameter table, a click on a parameter's name opens its detail popup, whose
**Link…** picks the parameter to follow and **Unlink** detaches it; the
table's right-click menu offers the same (**Fig.36**). **Tools → Views → Global
View** draws every open fit, its parameters and their links as a network
(**Fig.37**): click a parameter node to select it (it shows in the *Selection*
table), click a second one and press **Link**: the first one selected is the
master, the second follows it. A parameter can also be dragged onto the one it
should follow. **Unlink** removes the links of the selected parameters -- with
**all** ticked, of every parameter in every fit.

```{image} figures/manual_parameter_link.png
:align: center
```

**Fig.36 A linked lifetime.** Two lifetime fits of IBH sample decays, the
lifetime `t0` of the second linked to that of the first. (**a**) The second
fit's Lifetimes table: the linked τ_L is drawn in grey italics and shows the
value it follows. (**b**) Its detail popup: `t0 → t0` names the parameter it
follows, and **Unlink** is enabled.

```{image} figures/manual_global_view.png
:align: center
```

**Fig.37 The same two fits in Global View.** Fits are blue, free parameters
purple; the link is the arrow from the follower `t0` (selected, shown in the
*Selection* table with its role *follower*) to the parameter it follows. The
status line counts owners, parameters and links.
