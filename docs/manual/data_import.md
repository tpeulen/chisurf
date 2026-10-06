---
type: Manual Page
title: Data import
description: Internally, all imported data is managed in a single list (chisurf.imported_datasets).
tags: [manual, data, import]
---

# Data import

```{image} figures/main_read_data_dock.png
:align: center
```

Internally, all imported data is managed in a single list (**chisurf.imported_datasets**). Its elements are instances of **chisurf.data.ExperimentalData**. The user interface helps populating the dataset list (**Fig.4**).

**Fig.4 The Read data dock.** At the top, **Experiment** selects the experiment type (here TCSPC) and **File type** the reader for it (here TXT/CSV); **+ Data** reads a file and **?** opens the reader's help. Below, under **File parameters**, the reader's settings: the *Format* (column detection, header rows to skip, which columns hold x, y and their errors), *Timing* (time per channel, rebinning, repetition rate) and *Anisotropy (VV/VH)*. Shown are the settings for the IBH sample decays: 10 header rows and 0.0141 ns per channel. Files can also be dropped on the dock ("Drop files here").

To read data using the graphic user interface, first select the corresponding experiment type (**Fig.4**, 1). Afterwards select the file type of the experiment (**Fig.4**, 2). Before reading data, check the parameters that are passed to the data read (**Fig.4**, 3). Finally, you can load the dataset into ChiSurf, either by clicking on the "**+ Data**" button or using the key combination "**Ctrl+N**" (Windows, Linux) or "**⌘+N**" on macOS. Alternatively, multiple files of the same kind can be opened in a single step by selecting the respective files in a file explorer of your choice and dragging the selected files into the user interface to the dataset list (**Fig.5**).

Every action taken in the interface has an equivalent in the shell, and is echoed there as it happens — reading a file appends the same call to the session history:

```{image} figures/main_datasets_loaded.png
:align: center
```

**Fig.5 The data list after an import.** The four files of the IBH sample read with the settings of Fig.4, each with its index, name and data type. Dropping files from a file browser onto this list reads them the same way, with the current reader.

Alternatively, files can be opened programmatically using the shell:

```
chisurf.macros.add_dataset(filename='/Users/tpeulen/dev/chisurf/test/data/tcspc/ibh_sample/Decay_577D+577A+GTPgS.txt')
```

The called macro will add open a dataset for the currently selected setup and with the current parameters for reading files. Programmatically, the current setup and the reading routing can be changed from the shell by assigning values to the **cs.current_experiment** and the **cs.current_setup** variable. For instance:

```
cs.current_experiment = 'FCS'
cs.current_setup = 'Seidel Kristine'
```

Interactions with the graphical user interface are reflecting as commands in the programming shell.

The context menu of the data list can be used to save, load, remove, group and ungroup datasets (**Fig.6**). Dataset of equal data type can be group into groups. Grouping dataset can be useful when analyzing datasets of similar type, e.g., when analyzing titration data.

```{image} figures/main_datasets_context_menu.png
:align: center
```

**Fig.6 Dataset context menu.** A right click on the data list offers **Save**, **Load**, **Remove**, **Group**, **Ungroup** and **Refresh** (redraw the list) for the selected datasets.

To group datasets, select the corresponding dataset in the data set list and select in the context menu (right click) the group option (**Fig.7**).

```{image} figures/main_datasets_grouped.png
:align: center
```

**Fig.7 Grouped datasets.** The two decays grouped with **Group**: in the data list the group is one entry, unfolded here to show its members. In the **Console**, the group is one element of `cs.imported_datasets` and iterates over its members.

In the shell datasets are grouped as follows:

```
chisurf.macros.group_datasets([1, 2])
```

Here, the numbers refer to the index of the dataset in the **chisurf.imported_datasets** list. The order of datasets in the list can be changed by editing the number of the dataset in the first column of the data list (**Fig.4**). The currently selected dataset can be accessed in the shell:

```
cs.current_dataset
```

Datasets that are curves be accessed by their attributes.

```
import pylab as plt
cs.current_dataset
plt.plot(cs.current_dataset.x, cs.current_dataset.y)
```

For details look at the Application Programming Interfaces, API, of ChiSurf.
