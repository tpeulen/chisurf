---
type: Manual Page
title: Fit of the green-excitation FCS curve
description: Load three autocorrelation curves of a free green dye, fit them with a 3D Gaussian diffusion model with one bunching term, link the shared parameters and set up a global fit.
tags: [manual, fitting, fcs, plugins]
---

# Fit of the green-excitation FCS curve

```{seealso}
Theory — the correlation function, diffusion models and derived quantities:
{ref}`concept-fcs-correlation`. A shorter task-focused version:
{doc}`/guides/09_diffusion_fcs`.

```

Start ChiSurf. The first start can take a few seconds while the analysis
plugins are discovered.

The window has two halves. Left, the docks: **Read data** (experiment and file
type, **+ Data**), **Datasets**, **Analysis**, **Plot settings** and **Logging**,
with the Python **Console** below. Right, the working area: every analysis opens
in its own fit window.

```{image} figures/fcs_main_window.png
:align: center
```

In **Read data**, set **Experiment** to **FCS** and **File type** to the format of
your correlation files -- here **Seidel Kristine** (`.cor`). Load the files with
**+ Data** or **File → Add dataset** (⌘N), or drop them on the dock. The pictures
in this chapter use three repeated measurements of free Alexa 488
(`A488_ACF_1.cor` … `A488_ACF_3.cor`: the detector-1 autocorrelation of the three
Zeiss Confocor3 A488 measurements bundled in `test/data/fcs/confocor3`).

```{image} figures/fcs_datasets_added.png
:align: center
```

The curves are listed in the **Datasets** dock. Select them, choose
**Parse-Model** under **Model** and press **+ Analysis**:

```{image} figures/fcs_add_analysis.png
:align: center
```

One fit window opens per curve:

```{image} figures/fcs_fit_windows.png
:align: center
```

Caution! The windows may lie on top of each other. Maximise one to see one curve
at a time, or show them as tabs -- **View** and the toolbar arrange the
windows; with tabs, a click on a window's tab brings it to the front:

```{image} figures/fcs_fit_windows_tabbed.png
:align: center
```

Or tile them to cover the working area evenly:

```{image} figures/fcs_fit_windows_tiled.png
:align: center
```

Make the first window current and open the **Analysis** dock. Under
**Equation**, choose the formula **3D Gauss, 1 bunching** in **Model**; the
equation, its rendered form and a description appear beneath:

```{image} figures/fcs_model_3d_gauss_bunching.png
:align: center
```

The model has six parameters: the number of molecules in the focus (`N`), the
diffusion time (`td`), the shape factor of the detection volume (`s`, the ratio
of axial to lateral waist), the offset (`b`), and the amplitude and relaxation
time of the bunching term (`ba`, `bt`). They are listed under **Equation
parameters**, each with a **Fixed** box, optional bounds (**Lo**, **Hi**,
**Bounds**) and, after a fit, its **Error**.

Note: ChiSurf comes with a catalogue of predefined equations; you can modify them
or add your own models (see {doc}`adding_the_membranediffusion_models`).

```{image} figures/fcs_model_parameters.png
:align: center
```

Press **▶ Fit** (the **Fit** section of the dock):

```{image} figures/fcs_first_fit.png
:align: center
```

Fitted over the whole curve, the bunching term takes an amplitude of 0.97 at
75 ns and `N` drops to 0.17: it is fitting the first point (0.2 µs), which
carries the detector's afterpulsing, not the photophysics of the dye. A result
like this -- a relaxation time at the first lag point, an amplitude near 1 -- is
a sign that the fit range is wrong, not the model.

The table also gives an **Error** for each parameter, from the curvature of χ²
around the solution. It is **NOT** a reliable **uncertainty** of the fit result,
but it gives a first hint whether the uncertainty is rather large or small. What
it does and does not say -- and what to do instead -- is
{ref}`concept-parameter-uncertainty`.

For a more reliable estimate, ChiSurf can (i) scan the χ² surface (the
**Parameter scan** tab) or (ii) **Sample** the posterior, which also shows the
mutual dependencies between the parameters. That uncertainty analysis is beyond
the scope of this calibration and is shown in {doc}`/guides/39_parameter_uncertainty`.

Here, we take advantage of multiple measurements of the same sample and take these
as additional restraints.

First set the fit range: start at the second point (**First** 1) to leave out
the afterpulsing, and end at ~100 ms (**Last**), where the curve has reached its
baseline and only noise follows. Type the indices in the **Fit** section, or drag
the edges of the shaded range in the plot:

```{image} figures/fcs_fit_range.png
:align: center
```

*Of note*: To reliably fit your diffusion time, the **baseline** (0 or 1, depends
on the correlation algorithm) **MUST** **be reached** in your correlation curve
(or in the fit range, respectively).

Press **▶ Fit** again and observe the changes:

```{image} figures/fcs_second_fit.png
:align: center
```

Now `N` = 4.86, `td` = 25.6 µs, `s` = 7.26, and a bunching term of 21 % at
0.90 µs -- triplet blinking of the dye. The shape factor is at the upper end of
what a well-aligned confocal setup gives (about 3 to 7); on a single short
measurement it is poorly determined by the long-lag tail.

Now let's add the other measurements into the play and see whether a joint fit
stabilises this value.

Go to the other fit windows, choose **3D Gauss, 1 bunching**, set the same fit
range and fit them as done for the first curve:

```{image} figures/fcs_all_fitted.png
:align: center
```

The third curve, fitted alone, gives `s` = 10 and a negative bunching amplitude
-- more evidence that one measurement does not pin the volume down.

Next, we link the fits together so that shared parameters are minimised jointly.
Decide on one "parent" curve to which all others point -- here curve 1 -- and
make a "child" curve current.

**Right-click a parameter row** in **Equation parameters**: the menu offers
**🔗 Link *name* to**, listing every fit of the session, then that fit's
**Parameters**; pick the parameter to link to (**Unlink** drops a link again):

```{image} figures/fcs_link_menu.png
:align: center
```

For our joint fit, link (i) the diffusion time `td`, (ii) the shape factor `s`
and (iii) the bunching time `bt` of curves 2 and 3 to curve 1. Linked
parameters are shown greyed and in italics, with the value of the parameter they
follow:

```{image} figures/fcs_linked_parameters.png
:align: center
```

Then set up a global fit: in the **Datasets** dock select **Global Dataset**,
choose **Global fit** under **Model** and press **+ Analysis**:

```{image} figures/fcs_add_global_fit.png
:align: center
```

The global fit opens as a fit window of its own. In its **Analysis** dock, pick
each curve's fit in **Add** and press **➕ Add**, so that **Local fits** lists the
three curves (**➖ Remove** and **🗑 Clear** take them out again; there is no need
to keep the global fit out of its own list). Press **▶ Fit**: all curves are now
fitted jointly, with the linked `td`, `s` and `bt` shared and `N` and `ba` free
per curve. Read the joint values on the global fit's **Info** tab.

If you fit many and / or complicated models, a fit can take a while; a progress
dialog shows how far it is.

Finally, save the fits with **File → Fits → Current Fit** (⌥⌘S) or **All Fits**:

```{image} figures/fcs_file_menu.png
:align: center
```

Save the results of all measurements, we will need the fit results in the next step.
