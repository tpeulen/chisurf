# ChiMOL demo scripts

Plain ChiMOL scripts, one command per line, run with `@` exactly as PyMOL runs a
`.pml`:

```text
@demos/cartoon.pml
```

They exist for two reasons and both matter:

* **to try ChiMOL without a lot of clicking** — the Demo menu runs each of these,
  so the viewer can be exercised end to end in one action;
* **as a development harness.** Every line is a real command, so a demo that
  stops working is a command that stopped working. They are deliberately written
  in the ChiMOL/PyMOL command language rather than in Python: that is what makes
  them a test of *language parity* rather than of the internals.

Keep them short, keep them readable, and prefer commands a PyMOL user would
recognise. A demo is documentation that runs.
