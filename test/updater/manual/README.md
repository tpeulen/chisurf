# Manual updater checks — not tests

These files were collected by pytest as `test_updater/test_*.py`, but none of
them is a test: no `test_` functions, no assertions, only prints. Several reach
the network, and two called `sys.exit()` at module scope — which pytest reports
as `INTERNALERROR` and which aborts the **entire** session, not just the file.

They were renamed `check_*.py` and moved here so pytest no longer collects them.
Nothing was deleted: each is still runnable on its own, which is how they were
used.

```bash
python test/updater/manual/check_updater.py
```

The four files left in `test/updater/` are the real tests. If you want any of
the checks below to actually guard something, give it a `test_` function with an
assertion and move it back up a level — a script that only prints cannot fail,
so it protects nothing.
