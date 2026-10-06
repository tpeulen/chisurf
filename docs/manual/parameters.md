---
type: Manual Page
title: Parameters
description: A key attribute of parameters is their value.
tags: [manual, parameters]
---

# Parameters

A key attribute of parameters is their value. Parameter values are either fixed or variable floating-point numbers. Parameters can be part of a model. Variable parameters associated to a model instance are varied during model fitting/optimization and model sampling. A parameter can be bounded to restrict its range during sampling/optimization. An instance of a parameter can be connected (linked) to another parameter instance ({doc}`linking_parameters`). A parameter that is linked to another parameter will report the value of the other parameter as its own value. This allows to introduce dependencies across different model instances.

```{image} figures/manual_parameter_table.png
:align: center
```

**Fig.10 Fitting parameters.** (**a**) Parameters are shown as rows of a table
in the Analysis dock, here the Convolution box of a lifetime fit: the *Value*,
*Fixed*, the lower and upper bound *Lo*/*Hi* with *Bounds* to enforce them, and
the fitted *Error*. Fixed parameters are drawn grey. (**b**) A click on a
parameter's name opens its detail popup, here for the IRF time shift *ts*
(`timeshift`): its link state (*Not linked*) with **Link…** and **Unlink**,
the value with *Fixed*, the **Prior**, and the bounds.

A parameter value is changed by editing its *Value* cell (**Fig.10**, **a**),
or in the popup (**b**). *Fixed* fixes it, *Bounds* enables the *Lo*/*Hi*
range. A parameter is linked to another one with **Link…** in its popup, or
from the table's right-click menu ({doc}`linking_parameters`); a linked
parameter shows its value in grey italics and the popup names the parameter it
follows.

Actions in the user interface on parameters can be called from the shell. In the ChiSurf shell script below, two parameters are created, values are assigned to the respective parameters, and parameters are linked to each other, to illustrate how to create and interact with parameters.

```
from chisurf.core.parameter import Parameter

p1 = Parameter(name='p1', value=0)
p2 = Parameter(name='p2', value=0)
p1.value = 1
p2.value = 2
p1.link = p2
p1.value == 2 # True
```

Links are removed by assigning None to a link attribute.

```
p1.link = None
p1.value == 1 # True
```

The variable parameters of the current fit model are accessed using the parameter_dict attribute.

```
cs.current_fit.model
cs.current_fit.model.parameter_dict
```

All parameters (fixed & variable) of the current fit model are accessed using the parameters_all_dict attribute.

```
cs.current_fit.model.parameters_all_dict
```

Parameter bounds can be enabled, assigned and disabled in the shell by setting the bounds_on attribute and assigning upper and lower bounds. Here, is an example for the parameter named 'sc'.

```
chisurf.fits[0].model.parameters_all_dict['sc'].bounds_on = True
chisurf.fits[0].model.parameters_all_dict['sc'].bounds = (0.0, 1.0)
chisurf.fits[0].model.parameters_all_dict['sc'].bounds_on = False
```

Parameters can be fixed and made variable parameter as follows:

```
chisurf.fits[0].model.parameters_all_dict['sc'].fixed = True
chisurf.fits[0].model.parameters_all_dict['sc'].fixed = False
```

Fixed parameters are not varied during fitting and sampling.
