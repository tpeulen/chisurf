# Reference fixtures for the ebFRET port

`test_octave_ab.py` compares the Python port with ebFRET's own MATLAB code
without needing either at test time. `make_fixtures.m` runs ebFRET's
`+analysis`/`+plot` functions under Octave on six traces of the vendored
`simulated-K04-N350` dataset and writes `../data/octave/*.json` (full double
precision, arrays column-major); regenerate with
`EBFRET_SRC=<ebfret-gui>/src octave --no-gui -q make_fixtures.m` from this
directory (the default source is `junk/ebFRET/src`; the driver works on a
temporary copy in which only Octave-incompatible `import` shortcuts and one dead
condition are rewritten). `extract_session_fixture.py <session.mat>` cuts the
four-state analysis of 12 series out of ebFRET's shipped, MATLAB-saved
`simulated-K04-N350-ebfret-session.mat` into `../data/ebfret_session_k4.json`,
the check against a real MATLAB run with the compiled MEX kernels.
