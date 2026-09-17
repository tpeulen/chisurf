% Record the file-format fixtures of burst_ebfret's io tests with ebFRET itself.
%
% Run from the plugin directory with GNU Octave and an ebFRET checkout:
%
%   cd chisurf/plugins/burst/burst_ebfret/tests/data/io
%   octave --no-gui -q --eval "ebfret_src='/path/to/ebfret-gui/src'; \
%       source('../../octave/make_io_fixtures.m')"
%
% Everything written here is small; the tests read it without Octave.
if ~exist('ebfret_src', 'var')
    ebfret_src = fullfile(getenv('HOME'), 'dev', 'chisurf', 'junk', 'ebFRET', 'src');
end
addpath(genpath(ebfret_src));

% --- load_raw: unstacked (donor/acceptor column pairs), first row = labels
unstacked = [7 1 12 2;
             100 200 110 190;
             101.5 199.5 120 180;
             99 201 130 170;
             98.25 202 140 160];
save('-ascii', 'raw_unstacked.dat', 'unstacked');
[don, acc, lab] = ebfret.io.load_raw('raw_unstacked.dat', 'has_labels', true);
out = struct('donors', {don}, 'acceptors', {acc}, 'labels', lab);
fid = fopen('raw_unstacked_octave.json', 'w'); fprintf(fid, '%s', jsonencode(out)); fclose(fid);

% --- load_raw: stacked [id donor acceptor] with a gap in the ids
stacked = [1 176.03321 163.30509;
           1 180.41034 158.92795;
           1 158.85143 180.48687;
           3 42 0;
           3 150 160;
           3 151 159;
           3 152 158];
save('-ascii', 'raw_stacked_gap.dat', 'stacked');
[don, acc, lab] = ebfret.io.load_raw('raw_stacked_gap.dat', 'has_labels', true);
out = struct('donors', {don}, 'acceptors', {acc}, 'labels', lab);
fid = fopen('raw_stacked_gap_octave.json', 'w'); fprintf(fid, '%s', jsonencode(out)); fclose(fid);

% --- load_sf_tracer: two header lines, then region channel area length bg I1..IT
fid = fopen('sf_tracer.tsv', 'w');
fprintf(fid, 'background 10 foreground 20 cutoff 3\n');
fprintf(fid, 'region\tchannel\tarea\tlength\tbackground\tI1\tI2\tI3\n');
fprintf(fid, '0\t0\t9\t3\t5\t105\t106\t107\n');
fprintf(fid, '0\t1\t9\t3\t2\t202\t203\t204\n');
fprintf(fid, '1\t0\t9\t3\t1\t11\t12\t13\n');
fprintf(fid, '1\t1\t9\t3\t0\t21\t22\t23\n');
fclose(fid);
[don, acc] = ebfret.io.load_sf_tracer('sf_tracer.tsv');
out = struct('donors', {don}, 'acceptors', {acc});
fid = fopen('sf_tracer_octave.json', 'w'); fprintf(fid, '%s', jsonencode(out)); fclose(fid);

% --- a session as save_data.m writes it (old-style numeric group labels)
series = struct('file', {'a', 'a', 'b'}, ...
                'label', {'1', '2', '3'}, ...
                'group', {1, 1, 2}, ...
                'time', {(1:4)', (1:3)', (1:5)'}, ...
                'signal', {[0.1; 0.2; 0.3; 0.4], [0.5; 0.6; 0.7], [0.2; 0.2; 0.8; 0.8; 0.2]}, ...
                'donor', {[9; 8; 7; 6], [5; 4; 3], [8; 8; 2; 2; 8]}, ...
                'acceptor', {[1; 2; 3; 4], [5; 6; 7], [2; 2; 8; 8; 2]}, ...
                'crop', {struct('min', 1, 'max', 4), struct('min', 2, 'max', 3), ...
                         struct('min', 1, 'max', 5)}, ...
                'exclude', {false, false, true});
prior = struct('pi', [1; 2], 'A', [10 1; 2 20], 'mu', [0.2; 0.7], ...
               'beta', [0.5; 0.25], 'W', [30; 40], 'nu', [3; 4]);
analysis = struct('dim', {[], struct('states', 2)}, ...
                  'prior', {[], prior}, ...
                  'posterior', {[], []}, ...
                  'expect', {[], []}, ...
                  'lowerbound', {[], [1.5 -2.25 0]}, ...
                  'viterbi', {[], []}, ...
                  'restart', {[], [0 2 0]});
post = prior; post.mu = [0.15; 0.75]; post.A = [11 2; 3 21];
empty_post = struct('pi', [], 'A', [], 'mu', [], 'beta', [], 'W', [], 'nu', []);
analysis(2).posterior = [post, prior, empty_post];
e = struct('z', [2.5; 0.5], 'z1', [1; 0], 'zz', [2 0.5; 0 0.5], 'x', [0.2; 0.4], 'xx', [0.05; 0.17]);
analysis(2).expect = [e, e, struct('z', [], 'z1', [], 'zz', [], 'x', [], 'xx', [])];
analysis(2).viterbi = [struct('state', [1; 1; 2; 2], 'mean', [0.15; 0.15; 0.75; 0.75]), ...
                       struct('state', [2; 2], 'mean', [0.75; 0.75]), ...
                       struct('state', [], 'mean', [])];
controls = struct('colors', struct('obs', [0.4 0.4 0.4]), ...
                  'show', struct('viterbi', 1, 'prior', 0, 'posterior', 1), ...
                  'series', struct('value', 2, 'min', 1, 'max', 3), ...
                  'ensemble', struct('min', 2, 'max', 3, 'value', 2), ...
                  'min_states', 2, 'max_states', 3, ...
                  'clip', struct('min', -0.2, 'max', 1.2), ...
                  'init_restarts', 5, 'restarts', 1, 'all_restarts', 4, ...
                  'run_analysis', 0, 'run_all', 0, 'run_precision', 1e-4, ...
                  'scale_plots', 0, 'crop_margin', 7);
plots = struct();
save('-v7', 'session_octave.mat', 'controls', 'series', 'analysis', 'plots');

% --- write_report on a report-shaped struct array
rep(1).Series.Label = 'all';
rep(1).Series.Number = 3;
rep(1).Series.Length.Mean = 12.5;
rep(1).Series.Length.Std = 0.25;
rep(1).Statistics.Label = {'all', ''};
rep(1).Statistics.Num_States = {'2', ''};
rep(1).Statistics.State = [1; 2];
rep(1).Statistics.Occupancy.Fraction = [0.25; 0.75];
rep(1).Parameters.Transition_Matrix.Mean = [0.9 0.1; 0.2 0.8];
rep(2).Series.Label = 'group 1';
rep(2).Series.Number = 1;
rep(2).Series.Length.Mean = -1.5e-7;
rep(2).Series.Length.Std = 1234567;
rep(2).Statistics.Label = {'group 1', ''};
rep(2).Statistics.Num_States = {'2', ''};
rep(2).Statistics.State = [1; 2];
rep(2).Statistics.Occupancy.Fraction = [0.5; 0.5];
rep(2).Parameters.Transition_Matrix.Mean = [0.7 0.3; 0.4 0.6];
ebfret.io.write_report('report_octave.csv', rep);
