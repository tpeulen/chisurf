# F-test and χ²-max — is the extra parameter justified?

Adding parameters to a model can only lower χ². This calculator asks whether the
drop is larger than fitting noise would produce, and how far χ² may rise above a
fit's minimum before a parameter set is excluded.

## F-test — two nested models

Load the **simpler** fit as model 1 and the **more complex** one as model 2 with
**📊 From fit**, or type χ²r and ν = points − free parameters.

- **confidence** = F.cdf(χ²r₁ / χ²r₂; n₁, n₂). Above ~0.95 the extra parameters
  are justified by this test; 0.5 means no preference.
- Editing **confidence** solves the other way: the χ²r₂ the complex model must
  reach, χ²r₁ / F.ppf(conf; n₁, n₂). It overwrites **χ²(2)**.

This is the **variance-ratio** form, which treats the two χ² as independent. Two
fits of the same data are not, so it is conservative: on a real decay it gave
0.59 where the extra-sum-of-squares F test gave p = 0.003. For a sharper answer
compute F = ((χ²₁ − χ²₂)/(ν₁ − ν₂)) / (χ²₂/ν₂) against F(ν₁ − ν₂, ν₂).

## χ²-max — the confidence threshold of one fit

χ²max = χ²min · (1 + p/ν · F(p, ν; conf)). Parameter sets with χ²r below it are
inside the joint confidence region of p parameters. For a single parameter's
interval set **params** to 1.

## Before trusting either

- χ²r of the complex model should be near 1; systematic misfit makes every test
  here meaningless.
- The models must be nested and fitted over the same window with the same
  weights.
- A component on a bound (a lifetime at its limit, an amplitude near zero) is not
  resolved, whatever the confidence says.

## Further reading

- [Model comparison and batch fits](docs/guides/78_model_comparison_and_batch.md)
  — this tool on real fits, and where the tests disagree.
- [Comparing nested models: the F-test](docs/concepts/fitting_objectives.md) —
  the statistics, assumptions, AIC and BIC.
- [Parameter uncertainty](docs/concepts/parameter_uncertainty.md) — intervals
  from the same threshold.
