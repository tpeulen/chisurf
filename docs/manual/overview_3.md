---
type: Manual Page
title: 'Global view: overview'
description: In ChiSurf dependencies between parameters can be introduced by linking and visualized in graphs (Fig.31).
tags: [manual, fitting, global-analysis]
---

# Global view: overview

In ChiSurf dependencies between parameters can be introduced by linking and visualized in graphs (**Fig.31**). The *Global view* plugin (*i*) visualizes parameter dependencies in directed graphs, (*ii*) saves parameter dependencies, and (*iii*) restores dependencies from files.

```{image} _images/image_rId43.png
:align: center
```

**Fig.31. Parameter dependency graph in time-resolved fluorescence decay analysis.** Four fluorescence decays are analysed jointly: the donor in a donor-only sample, $f_{D(0)}$; the donor in the presence of an acceptor, $f_{D(A)}$; the directly excited acceptor in the FRET sample, $f_{A}$; and the FRET-sensitised acceptor emission, $f_{A(D)}$. Parameters and models are represented by circles. Dependencies are illustrated by arrows. Parameters dependent on other parameters are colored in green. Fixed parameters are displayed in light green. Variable parameters are highlighted in magenta.

```{image} _images/image_rId44.png
:align: center
```

The *Global view* plugin opens from the Plugin menu, Plugins → Global view, in a separate window (**Fig.32**).

**Fig.32.** User interface of the *Global view* plugin. The plugin represents models and parameters in graphs (bottom). The Visualization group box of the plugin gathers options controlling the graph visualization (Node size, Graph scale). The Network group box can be used to save and load dependencies. The Link group box can be used to introduce and delete (clear) dependencies across selected and all parameters.
