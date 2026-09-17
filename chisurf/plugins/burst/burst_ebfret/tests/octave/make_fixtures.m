% make_fixtures.m -- record ebFRET reference numbers for test_octave_ab.py
%
% Run from this directory:
%
%   EBFRET_SRC=path/to/ebFRET/src octave --no-gui -q make_fixtures.m
%
% EBFRET_SRC defaults to the junk/ebFRET/src reference checkout.
%
% Octave cannot run `import` inside a function, and three of ebFRET's files
% use it to shorten `ebfret.analysis.hmm.` to `hmm.`. The driver therefore
% copies the .m sources to a temporary directory and spells those names out in
% vbayes.m, report.m and dirichlet/tau.m -- a rename, nothing else (plus one
% dead condition Octave cannot parse, see make_shim). The macOS
% MEX files are not copied, so vbayes/viterbi_vb take their native MATLAB
% fallbacks, which is what the Python port follows.
1;

function shim = make_shim(src)
  shim = fullfile(tempdir(), 'ebfret_octave_shim');
  if exist(shim, 'dir')
    confirm_recursive_rmdir(false);
    rmdir(shim, 's');
  end
  mkdir(shim);
  system(sprintf('rsync -a --include="*/" --include="*.m" --exclude="*" "%s/" "%s/"', src, shim));
  files = {'+ebfret/+analysis/+hmm/vbayes.m', '+ebfret/+analysis/+hmm/report.m', ...
           '+ebfret/+analysis/+dist/+dirichlet/tau.m'};
  for i = 1:numel(files)
    f = fullfile(shim, files{i});
    text = fileread(f);
    text = regexprep(text, '(?m)^\s*import ebfret\.analysis[^\n]*$', '');
    text = regexprep(text, '(?<![\w.])hmm\.', 'ebfret.analysis.hmm.');
    text = regexprep(text, '(?<![\w.])dist\.', 'ebfret.analysis.dist.');
    fid = fopen(f, 'w'); fprintf(fid, '%s', text); fclose(fid);
  end
  % dirichlet/h_step.m tests `(nargin > 2) and length(weights(:)) == 1`, which
  % Octave cannot parse; there is no `weights` argument, so the branch is dead
  % and the shim writes its value, `false`.
  f = fullfile(shim, '+ebfret/+analysis/+dist/+dirichlet/h_step.m');
  text = fileread(f);
  text = strrep(text, '(nargin > 2) and length(weights(:)) == 1', 'false');
  fid = fopen(f, 'w'); fprintf(fid, '%s', text); fclose(fid);
end

function t = numstr(x)
  if isnan(x)
    t = '"NaN"';
  elseif isinf(x)
    if x > 0, t = '"Inf"'; else, t = '"-Inf"'; end
  else
    t = sprintf('%.17g', x);
  end
end

function s = J(v)
  % JSON with full double precision; arrays as {"shape", "data"} (column-major)
  if isstruct(v)
    if numel(v) ~= 1
      parts = {};
      for i = 1:numel(v)
        parts{end+1} = J(v(i));
      end
      s = ['[' strjoin(parts, ',') ']'];
    else
      f = fieldnames(v);
      parts = {};
      for i = 1:numel(f)
        parts{end+1} = ['"' f{i} '":' J(v.(f{i}))];
      end
      s = ['{' strjoin(parts, ',') '}'];
    end
  elseif iscell(v)
    parts = {};
    for i = 1:numel(v)
      parts{end+1} = J(v{i});
    end
    s = ['[' strjoin(parts, ',') ']'];
  elseif ischar(v)
    s = ['"' strrep(v, '"', '\"') '"'];
  else
    v = double(v);
    d = v(:)';
    strs = arrayfun(@numstr, d, 'UniformOutput', false);
    shape = sprintf('%d,', size(v));
    s = ['{"shape":[' shape(1:end-1) '],"data":[' strjoin(strs, ',') ']}'];
  end
end

function write_fixture(name, data)
  fid = fopen(fullfile('..', 'data', 'octave', [name '.json']), 'w');
  fprintf(fid, '%s\n', J(data));
  fclose(fid);
end

function [post, E, vit, lb, rs] = vb_series(x, u, w_prev, restarts, threshold)
  % body of MainWindow/run_vbayes.m's parfor loop (restarts <= 1: no draws)
  w0 = u([]);
  if ~isempty(w_prev) && ~isempty(w_prev.mu)
    w0(end+1) = w_prev;
  end
  if restarts > 0
    w0(end+1) = ebfret.analysis.hmm.init_posterior(x, u);
  end
  vb = struct();
  for r = 1:length(w0)
    [vb(r).w vb(r).L vb(r).E] = ebfret.analysis.hmm.vbayes(x, w0(r), u);
  end
  L_max = vb(1).L(end);
  r_max = 1;
  for r = 2:length(vb)
    if (vb(r).L(end) - L_max) > 1e-2 * threshold * abs(L_max) || isnan(L_max)
      r_max = r;
      L_max = vb(r).L(end);
    end
  end
  lb = vb(r_max).L(end);
  post = vb(r_max).w;
  rs = r_max + restarts - length(w0);
  [vit.state, vit.mean] = ebfret.analysis.hmm.viterbi_vb(post, x);
  E.z = sum(vb(r_max).E.gamma(2:end,:), 1)';
  E.z1 = vb(r_max).E.gamma(1, :)';
  E.zz = squeeze(sum(vb(r_max).E.xi, 1));
  E.x = vb(r_max).E.xmean(:);
  E.xx = vb(r_max).E.xvar + vb(r_max).E.xmean.^2;
end

% ------------------------------------------------------------------------- %
src = getenv('EBFRET_SRC');
if isempty(src)
  src = fullfile('..', '..', '..', '..', '..', '..', 'junk', 'ebFRET', 'src');
end
warning('off', 'all');
addpath(make_shim(src));

dat = load(fullfile('..', 'data', 'simulated-K04-N350', 'raw-stacked.dat'));
ids = [2 4 5 7 10 14];
N = numel(ids);
x = {};
don = {};
acc = {};
for n = 1:N
  % load_raw.m with has_labels: the first row of each trace is its label
  rw = dat(dat(:,1) == ids(n), 2:3);
  rw = rw(2:end, :);
  don{n} = rw(:, 1);
  acc{n} = rw(:, 2);
  T = 130 - 10 * n;
  x{n} = (rw(1:T, 2) + eps) ./ (rw(1:T, 2) + rw(1:T, 1) + eps);
end

% ---- inputs, priors, one trace in detail -------------------------------- %
core = struct();
core.ids = ids;
core.x = x;
[core.x_lim_min, core.x_lim_max] = ebfret.analysis.x_lim(cat(1, x{:}));
core.u2 = ebfret.analysis.hmm.guess_prior(x, 2);
u = ebfret.analysis.hmm.guess_prior(x, 3);
core.u3 = u;
theta.mu = [0.1; 0.5; 0.9]; theta.lambda = [100; 200; 400]; theta.tau = [10; 50; 200];
counts.mu = [0.1; 0.2; 0.3]; counts.lambda = [5; 10; 20]; counts.tau = [3; 4; 5];
core.init_prior = ebfret.analysis.hmm.init_prior(theta, counts);

x1 = x{1};
w0 = ebfret.analysis.hmm.init_posterior(x1, u);
core.w0 = w0;
[core.E_ln_pi, core.E_ln_A, core.E_ln_px_z] = ebfret.analysis.hmm.e_step(w0, x1);
[g, xi, ln_Z] = ebfret.analysis.hmm.forwback_native(exp(core.E_ln_px_z), exp(core.E_ln_A), ...
                                                    exp(core.E_ln_pi));
core.gamma = g; core.xi = xi; core.ln_Z = ln_Z;
core.kl_w0_u = ebfret.analysis.hmm.kl_div(w0, u);
[core.m_step_w, core.m_step_ev] = ebfret.analysis.hmm.m_step(u, x1, g, xi);
[w, L, Ev] = ebfret.analysis.hmm.vbayes(x1, w0, u);
core.vbayes_w = w; core.vbayes_L = L; core.vbayes_xmean = Ev.xmean; core.vbayes_xvar = Ev.xvar;
[core.viterbi_state, core.viterbi_mean] = ebfret.analysis.hmm.viterbi_vb(w, x1);
core.dirichlet_tau = ebfret.analysis.dist.dirichlet.tau(w.A);
core.normwish_kl = ebfret.analysis.dist.normwish.kl_div(w, u);
core.dirichlet_kl_A = ebfret.analysis.dist.dirichlet.kl_div(w.A, u.A);
core.dirichlet_kl_pi = ebfret.analysis.dist.dirichlet.kl_div(w.pi, u.pi);
core.valid = ebfret.analysis.hmm.valid_prior(w);
write_fixture('core', core);

% ---- three empirical-Bayes iterations (run_ebayes.m, restarts 1) -------- %
precision = 1e-9;
max_iter = 2;
P = cell(N, 1);
eb = struct();
eb.precision = precision; eb.restarts = 1; eb.max_iter = max_iter;
eb.prior0 = u;
L = [];
it = 1;
while true
  Pc = {}; Ec = {}; Vc = {}; LB = zeros(1, N); RS = zeros(1, N);
  for n = 1:N
    [Pc{n}, Ec{n}, Vc{n}, LB(n), RS(n)] = vb_series(x{n}, u, P{n}, 1, precision);
  end
  P = Pc;
  L(it) = sum(LB);
  eb.(sprintf('lowerbound_%d', it)) = LB;
  eb.(sprintf('restart_%d', it)) = RS;
  if it > max_iter
    break
  end
  if it > 1 && (L(it) - L(it-1)) < precision * abs(L(it))
    break
  end
  u = ebfret.analysis.hmm.h_step([Pc{:}], u, 'expect', [Ec{:}]);
  eb.(sprintf('prior_%d', it + 1)) = u;
  it = it + 1;
end
eb.L = L;
eb.posterior = [Pc{:}];
eb.expect = [Ec{:}];
eb.viterbi = [Vc{:}];
eb.prior = u;
eb.h_step_no_expect = ebfret.analysis.hmm.h_step([Pc{:}]);
Ws = [Pc{:}];
[eb.ng_m, eb.ng_beta, eb.ng_a, eb.ng_b] = ebfret.analysis.dist.normgamma.h_step( ...
    cat(2, Ws.mu), cat(2, Ws.beta), 0.5 * cat(2, Ws.nu), 0.5 ./ cat(2, Ws.W), 1);
eb.dir_A = ebfret.analysis.dist.dirichlet.h_step(cat(3, Ws.A));
eb.dir_pi = ebfret.analysis.dist.dirichlet.h_step(cat(2, Ws.pi));
write_fixture('ebayes', eb);

% ---- summary: remap and report ----------------------------------------- %
E = [Ec{:}];
rep = struct();
[rep.remap_u, rep.remap_w, rep.remap_e] = ebfret.analysis.hmm.h_step_remap(u, E);
[rep.merge_u, rep.merge_w, rep.merge_e] = ebfret.analysis.hmm.h_step_remap(u, E, [1 1 2]);
rep.report = ebfret.analysis.hmm.report(x, u, E, 'lowerbound', LB, ...
                                        'splits', {1:N, [1 3 5]}, 'labels', {'all', 'odd'});
write_fixture('report', rep);

% ---- photobleaching ----------------------------------------------------- %
pb = struct();
pb.donor = don{6};
pb.acceptor = acc{6};
[pb.donor_index, pb.donor_d] = ebfret.analysis.photobleach_index(don{6});
[pb.acceptor_index, pb.acceptor_d] = ebfret.analysis.photobleach_index(acc{6});
step = [200 * ones(60, 1); 5 * ones(40, 1)] + 10 * sin((1:100)');
pb.step = step;
[pb.step_index, pb.step_d] = ebfret.analysis.photobleach_index(step);
write_fixture('photobleach', pb);

% ---- plot data (refresh.m) ---------------------------------------------- %
pl = struct();
xc = cat(1, x{:});
st = cat(1, eb.viterbi.state);
colors = ebfret.plot.line_colors(3);
pl.bins = ebfret.plot.get_bins(xc, 200, min(0.5 ./ N, 1e-2));
[pl.whist_counts, pl.whist_bins] = ebfret.plot.whist(xc, pl.bins, 'state', st, 'num_states', 3);
obs = ebfret.plot.state_obs(xc, 'state', st, 'xdata', pl.bins, 'num_states', 3, ...
                            'color', colors, 'linestyle', '-');
pl.obs = obs;
[pl.obs_xlim, pl.obs_ylim] = ebfret.plot.get_lim(obs, 1e-2, [0.05, 0.05, 0.05, 0.15]);
u_a = 0.5 .* u.nu; u_b = 0.5 ./ u.W;
pl.prior_mean = ebfret.plot.state_mean(u.mu, u.beta, u_a, u_b, 'linestyle', '--', 'color', colors);
pl.prior_noise = ebfret.plot.state_stdev(u_a, u_b, 'linestyle', '--', 'color', colors);
pl.prior_dwell = ebfret.plot.state_dwell(u.A, 'linestyle', '--', 'color', colors);
W = eb.posterior;
w_m = cat(2, W.mu); w_beta = cat(2, W.beta); w_a = 0.5 * cat(2, W.nu);
w_b = 0.5 ./ cat(2, W.W); w_alpha = cat(3, W.A);
pl.post_mean = ebfret.plot.mean(ebfret.plot.state_mean(w_m, w_beta, w_a, w_b, ...
                                'linestyle', '-', 'color', colors));
pl.post_noise = ebfret.plot.mean(ebfret.plot.state_stdev(w_a, w_b, 'linestyle', '-', ...
                                 'color', colors));
E_tau = -1 ./ log(diag(ebfret.normalize(mean(w_alpha, 3), 2)));
pl.post_dwell = ebfret.plot.mean(ebfret.plot.state_dwell(w_alpha, ...
    'xdata', arrayfun(@(tau) exp(linspace(log(0.01 * tau), log(100 * tau), 101))', ...
                      E_tau(:)', 'UniformOutput', false), ...
    'linestyle', '-', 'color', colors));
scale = mean(cat(2, eb.expect.z), 2);
pl.scale = scale;
names = {'mean', 'noise', 'dwell'};
thresholds = [0.02, 0.02, 0.001];
for a = 1:3
  lines = cat(1, ebfret.plot.scale(pl.(['prior_' names{a}])(:), scale), ...
              ebfret.plot.scale(pl.(['post_' names{a}])(:), scale));
  [xl, yl] = ebfret.plot.get_lim(lines, thresholds(a), [0.05, 0.05, 0.05, 0.25]);
  if strcmp(names{a}, 'dwell')
    xl = [max(1e-4 * xl(2), xl(1)), xl(2)];
  end
  pl.([names{a} '_xlim']) = xl;
  pl.([names{a} '_ylim']) = yl;
end
[vs, vm] = ebfret.analysis.hmm.viterbi_vb(W(1), x{1}(11:100));
pl.ts_state = vs;
pargs = struct('crop', struct('min', 11, 'max', 100), 'markersize', 4);
pargs.color = {[0.4, 0.4, 0.4], [0.66, 0.33, 0.33], colors{:}};
pargs.state = vs;
pargs.num_states = 3;
pl.time_series = ebfret.plot.time_series(x{1}, (1:numel(x{1}))', pargs);
pl.num_to_str_a = ebfret.num_to_str([0 0.2 0.25 1 10]);
pl.num_to_str_b = ebfret.num_to_str([0 0.001 1000 12345]);
write_fixture('plots', pl);

confirm_recursive_rmdir(false);
rmdir(fullfile(tempdir(), 'ebfret_octave_shim'), 's');
disp('fixtures written');
