---
type: Concept
title: The ChiSurf session
description: >-
  What datasets, fits, models and parameters are, how they relate, and which
  of them a number belongs to.
tags: [session, datasets, fits, models, parameters]
timestamp: '2026-07-25T00:00:00Z'
---

# Three things, in order

A session holds **datasets** and **fits**, and nothing else that matters.

* A **dataset** is a measured curve read from a file: x, y, and usually
  per-point uncertainties. It has an index, a name, and an *experiment type*
  (TCSPC, FCS, PDA, DEER, …) that decides which models can be applied to it.
* A **model** is a function of parameters that predicts what the measurement
  should look like. Its parameters have values, bounds, a fixed flag, and an
  error estimate.
* A **fit** binds one dataset to one model, plus the range of points to
  compare over. Running it varies the free parameters to minimise the
  disagreement.

A number therefore always belongs to *a fit*, not to a dataset. "The lifetime
of this sample" means "the lifetime parameter of the model in the fit of that
sample's dataset", and it changes when the model or the range changes.

# The numbers a fit produces

* **chi-square, reduced** (`chi2r`) — the disagreement per degree of freedom.
  Near 1 the model describes the data within the noise. Far above 1 the model
  is wrong, or the range includes something it should not. Far below 1 the
  uncertainties are overestimated.
* **degrees of freedom** — points in the fit range minus free parameters.
  Fixing or linking a parameter removes one, which is why both change chi2r.
* **Durbin-Watson** — near 2 when residuals are random. Well below 2 they are
  correlated, which means something systematic is left over even when chi2r
  looks acceptable. It is the more sensitive of the two.

# Fit ranges

A fit is only evaluated over its range. Narrowing it changes chi-square
without changing the model, so a range chosen after seeing the residuals is
not an innocent choice: excluding the region where a model disagrees makes
the number look better and the result worse.

A freshly created fit has no useful range until one is derived from the data;
ChiSurf's readers supply one.

# Fixed, linked, free

* **Free** — determined by this fit.
* **Fixed** — asserted by you, from a calibration or a reference. Any interval
  computed afterwards is conditional on it.
* **Linked** — one value shared across several fits, determined by all of
  them together. This is global analysis, and it is the only way to pin a
  parameter that a single measurement cannot constrain.

Which of the three a parameter is changes what the result *means*, so it
belongs in any report of that result.
