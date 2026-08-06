---
type: Reference
title: User-Defined Models in ChiSurf
description: Adding or changing fitting models without modifying the installed package.
tags: [reference, fitting, user, models]
---

# User-Defined Models in ChiSurf

This document explains how to add or change models **without modifying the
installed package**.

There are two independent mechanisms, and they solve different problems:

| | What it does | Use it when |
|---|---|---|
| **{ref}`Registering a model class <user-models-register>`** | Adds a *new* model to an experiment's model list | You wrote a new model |
| **{ref}`Override files <user-models-override>`** | Replaces the code of an *existing* module at startup | You want to tweak a built-in model |

Both read from your **user settings folder**, which is `~/.chisurf` on Windows,
Linux and macOS. You can confirm the location from a running ChiSurf with:

```python
from chisurf.core.settings.path_utils import get_path
print(get_path('settings'))          # -> ~/.chisurf
```

---

(user-models-register)=
## 1. Registering a new model class

ChiSurf builds each experiment's model list from **dotted class paths** listed in
`experiment_configs.yaml`. Adding a model therefore means writing an importable
class and naming it in that file — there is no registration decorator and no
folder that is auto-imported.

### 1.1 Write the model

A model is a subclass of `chisurf.core.models.model.Model`. For an ordinary 1-D
curve model, subclass `ModelCurve`, which combines `Model` with ChiSurf's curve
type. The only **abstract** method you must implement is `update_model`, which
computes the model from the current parameter values and the data on `self.fit`:

```python
import numpy as np
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.model import ModelCurve


class MyScaledModel(ModelCurve):
    """A minimal user model: the data scaled by one fitted parameter."""

    # The label shown in the GUI model dropdown.
    name = "My scaled model"

    def __init__(self, fit, **kwargs):
        super().__init__(fit, **kwargs)
        self.scale = FittingParameter(
            value=1.0, name='scale', lb=0.0, ub=100.0, bounds_on=True
        )

    def update_model(self, **kwargs):
        data = self.fit.data
        self.x = np.copy(data.x)
        self.y = self.scale.value * np.copy(data.y)
```

Fitting parameters are declared with
`chisurf.core.fitting.parameter.FittingParameter` and assigned to attributes;
they are discovered automatically because `Model` derives from
`FittingParameterGroup`, so nothing has to be registered by hand. `lb`/`ub` only
take effect when `bounds_on=True`.

For a model that needs its own Qt editor, subclass
`chisurf.gui.widgets.models.model_widget.ModelWidget` instead. Note that this is
**not** in `chisurf.core.models` — the compute model and its editor are
deliberately separate, and new models are expected to stay Qt-free and let the
editor be generated from a `.view.json` view spec (set `view_spec_file` on the
class). See {doc}`/development/index` for that framework.

### 1.2 Make it importable

The class path is resolved with a plain `importlib.import_module`, so the module
must be on `sys.path`. Any of these work:

- install your package (`pip install -e .`) into the same environment;
- put the module inside an existing importable package;
- set `PYTHONPATH` to the directory containing it before launching ChiSurf.

Dropping a `.py` file into `~/.chisurf/models/` is **not** enough on its own —
that folder is scanned only for `__override__` files (section 5), not imported as
a package.

### 1.3 List it in `experiment_configs.yaml`

Edit `~/.chisurf/experiment_configs.yaml` and add the dotted path under the
`models:` key of the experiment you want it to appear in:

```yaml
tcspc:
  models:
    - chisurf.gui.widgets.models.tcspc.LifetimeModelWidget
    - my_package.my_models.MyScaledModel        # <- your model
```

:::{warning}
**Lists replace, they do not merge.** The user file is deep-merged onto the
packaged default, but the merge recurses only into *dictionaries* — any list you
specify **replaces** the packaged list wholesale. If you write a `models:` block
containing only your model, you will lose every built-in model for that
experiment. Copy the packaged list and append to it.

The packaged default lives at
{src}`chisurf/core/settings/experiment_configs.yaml` inside the installation; use it
as the reference for what to copy.
:::

Your user copy is created on first run by `copy_settings_to_user_folder`, which
copies each packaged settings file **only if it does not already exist**. An
existing `~/.chisurf/experiment_configs.yaml` is therefore never refreshed
automatically, so a file written by an older ChiSurf will not gain experiments or
models added since. The boarding plugin can re-sync it from the packaged default
when entries appear to be missing.

### 1.4 Restart

Experiments are constructed once at startup (`init_setups` →
`_setup_experiment`). Restart ChiSurf; the model then appears in
`Experiment.model_names` and in the **Model** combobox for that experiment.

---

## 2. Which experiment key to use

Use the **top-level section key** from `experiment_configs.yaml` — `tcspc`,
`fcs`, `pda`, `stopped_flow`, and so on. Each such section carries its own
`readers:` and `models:` lists. The `experiment_types:` mapping at the top of the
file only sets each experiment's display `name` and `hidden` flag; models are
attached to the section key, not the display name.

If a section exists without a matching `experiment_types:` entry, ChiSurf still
creates an `Experiment` for it, so adding a new experiment section works even if
you forget the registry entry.

---

## 3. Turning a plain function into a model

For simple cases you do not need to write a class at all.
`chisurf.core.models.function_to_model_decorator` wraps a callable into a `Model`
subclass backed by a `chinet` node, deriving the fitting parameters from the
node's ports (output ports become fixed parameters):

```python
from chisurf.core.models import function_to_model_decorator

@function_to_model_decorator()
def my_callback():
    ...

# my_callback is now a Model subclass and can be listed in experiment_configs.yaml
```

---

## 4. Error handling and logging

Model setup is defensive at every step, which means **failures are silent in the
GUI and only visible in the log**:

- if the dotted path cannot be imported or the attribute is missing,
  `_resolve_class` logs `Failed to resolve class …` and returns `None`;
- if the class cannot be added, `_setup_experiment` logs
  `Failed to setup model … in <experiment>`;
- a broken user model never prevents the other models or experiments from
  loading.

If your model does not appear in the dropdown, check the ChiSurf log — a typo in
the dotted path and a module that is not importable both fail this way, and
neither raises a dialog.

---

(user-models-override)=
## 5. In-place model code editing (Front Face / Back Face)

This is the second mechanism: instead of adding a class, it **replaces the code
of an existing module** at startup.

### 5.1 Using the code view

Inside any **Fit Window** there is a **View Model Code** toggle above the plots
(the "Front Face"). It flips the view to the "Back Face" — a Python editor
holding the source of the active model.

### 5.2 Saving and applying changes

**Save and Apply Model** handles the change according to your permissions:

1. **Writable installations** — with write access to the original source file
   (e.g. an editable install), the change is written back to that file.
2. **Versioned user overrides** — in all cases a copy is written to
   `~/.chisurf/models/`, named for the fully-qualified module plus a timestamp,
   e.g. `chisurf.core.models.tcspc.fret__override__20260609_120000.py`.

### 5.3 Instant application and startup injection

The edited code is injected into the running session immediately, updating the
active fit. At every launch, `inject_user_models()` scans `~/.chisurf/models/`
for files containing `__override__`, groups them by module name, keeps the
**latest timestamp** per module, imports the original module, and executes the
override source in that module's namespace.

Two consequences follow from it being an `exec` into an existing module:

- the override **patches** the module rather than replacing the file, so names
  you do not redefine keep their original values;
- the target module must be importable — an override for a module that no longer
  exists logs `Failed to inject model override for …` and is skipped.

Only files whose name contains `__override__` are considered; any other `.py`
file in that folder is ignored.

### 5.4 Reverting changes

- Go to `~/.chisurf/models/`.
- Delete or rename the relevant `__override__` files.
- Restart ChiSurf to get the built-in code back.

---

## 6. Quick checklist

**Adding a new model**

- [ ] Write a `Model` / `ModelCurve` subclass implementing `update_model`.
- [ ] Set a short, descriptive `name` — it is the dropdown label.
- [ ] Make the module importable (installed package or `PYTHONPATH`).
- [ ] Add its dotted path to the `models:` list of the right experiment section
      in `~/.chisurf/experiment_configs.yaml`, **keeping the existing entries**.
- [ ] Restart ChiSurf and check the log if it does not appear.

**Changing a built-in model**

- [ ] Open the fit, toggle **View Model Code**, edit, **Save and Apply Model**.
- [ ] Confirm an `__override__` file appeared in `~/.chisurf/models/`.
- [ ] To revert, delete that file and restart.
