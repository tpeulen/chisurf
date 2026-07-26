addpath('/Users/tpeulen/dev/chisurf/junk/PAM/functions/BurstBrowser/GS_likelihood');
names = {'2state','2state_fast','3state_chain','3state_cycle'};
fid = fopen('octave.txt','w');
for i = 1:numel(names)
    n = names{i};
    t = load([n '_t.txt']);
    c = load([n '_c.txt']);
    K = load([n '_K.txt']);
    E = diag(load([n '_E.txt']));
    logL = GP_logL(t, c, K, E);
    fprintf(fid, '%s %.17e\n', n, logL);
end
fclose(fid);
