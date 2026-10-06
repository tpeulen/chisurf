---
type: Manual Page
title: Creating fits
description: In ChiSurf a Fit combines data with a model (Fig.3).
tags: [manual, fitting, creating, fits]
---

# Creating fits

```{image} figures/main_datasets_fits.png
:align: center
```

In ChiSurf a **Fit** combines data with a model (**Fig.3**). Fits are stored internally in the list **chisurf.fits**. New fits are added to this list using the graphical user interface in three steps (**Fig.8**).

**Fig.8 Creating fits in the Datasets dock.** The top list is the data list (index, name and data type of every imported dataset; here the four IBH sample files), the bottom list the fit list (index, dataset and model of every fit). Below it, **Model:** selects the model for the selected dataset and **+ Analysis** creates the fit, which opens its window (right).

In the first step, select a dataset in the data list by clicking on an item in the list (**Fig.8**, 1). In the second step, select a model for the selected dataset from the model selection dropdown menu (**Fig.8**, 2). In the third step, click the **+ Analysis** button next to the dropdown menu to create a new fit. In the first step, you can select multiple datasets of the same type by holding the Shift key while selecting data.

A new analysis can be created in the programming shell as follows:

```
chisurf.macros.add_fit(dataset_indices=[0], model_name="Lifetime")
```

`dataset_indices` is a list of integers and `model_name` is the model as it appears in the selector. The integers refer to the index in the **chisurf.imported_datasets** list. The order of fit can be changed by editing the number of the dataset in the first column of the fit/analysis list (**Fig.4**). Note, the order of the fits can matter, as parameters and variables of analysis are accessed through the fit index and the parameter name. Fits can also be created for grouped data sets. Selecting a fit in the fit list activates the corresponding fit window.
