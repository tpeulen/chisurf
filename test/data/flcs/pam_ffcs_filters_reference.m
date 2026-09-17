% A/B reference: PAM's two fFCS/FLCS filter calculations, run in Octave.
%
% Source: https://gitlab.com/PAM-PIE/PAM at commit 7319d15d. PAM computes the
% filters F = (D' W D)^-1 D' W, W = diag(1/Decay), in two places that differ
% only in how an empty total-decay bin is treated:
%
% (1) PAM.m, function Update_fFCS_GUI (main-window "Calculate Filters"):
%       lines 13911-13916  stack the selected PIE channels, normalise each pattern
%       lines 13954-13982  drop empty bins, renormalise, filters zero there
%     -> ChiSurf calc_ffcs_filters(..., empty_bins="exclude")
% (2) functions/BurstBrowser/Calc_fFCS_Filters.m:
%       lines 30-32  normalise patterns over all bins, empty bins set to 1
%       lines 54-58  W = diag(1/Decay_total)
%       lines 65-67  filters, reconstruction, weighted residuals
%     -> ChiSurf calc_ffcs_filters(..., empty_bins="unit_weight") (the default)
%
% The blocks below are copied verbatim; only the loop over PAM's two photon
% streams is fixed to u = 1, the GUI plotting between blocks is left out, and
% the inputs are bound to PAM's variable names first. Nothing else is needed, so
% this file regenerates the fixture without a PAM checkout;
% gen_pam_ffcs_filters_reference.py --pam <checkout> checks every copied block
% against a checkout line by line (junk/clone.sh re-clones one).
%
% Input  ab_input.mat : decay    (n_channels x LEN)  total micro-time histograms
%                       patterns (n_species x n_channels x LEN)
% Output ab_output.mat: filters, reconstruction           (1)
%                       filters_bb, reconstruction_bb,
%                       weighted_residuals_bb             (2)
%                       all on the stacked axis n_channels*LEN

load('ab_input.mat');
u = 1;
n_species = size(patterns, 1);
n_channels = size(patterns, 2);
active = 1:n_species;
Decay_Hist = {}; MI_Hist = {};
for j = 1:n_channels
    Decay_Hist{u}{1,j} = double(decay(j,:))';
    for i = active
        MI_Hist{u}{i,j} = double(reshape(patterns(i,j,:), [], 1));
    end
end

% --- PAM.m 13911-13916 (verbatim) ---
            %%% construct stacked channel
            PamMeta.fFCS.Decay_Hist{u} = vertcat(Decay_Hist{u}{:});
            for i = 1:size(MI_Hist{u},1)
                PamMeta.fFCS.MI_Hist{u}{i} = vertcat(MI_Hist{u}{i,:});
                PamMeta.fFCS.MI_Hist{u}{i} = PamMeta.fFCS.MI_Hist{u}{i}./sum(PamMeta.fFCS.MI_Hist{u}{i});
            end

% --- PAM.m 13954-13982 (verbatim) ---
            %%% calculate FLCS filters
            %%% problem: only those bins where Decay and all microtime patterns are
            %%% NOT zero are to be used!
            %%% all zero bins filter values should just be zero (so they don't
            %%% contribute to the correlation function)
            %%% solution: perform calculations only on "valid" bins
            valid = (PamMeta.fFCS.Decay_Hist{u} ~= 0);
            %for i = active
            %    valid = valid & (PamMeta.fFCS.MI_Hist{u}{i} ~= 0);
            %end
            Decay = PamMeta.fFCS.Decay_Hist{u}(valid);
            diag_Decay = zeros(numel(Decay));
            for i = 1:numel(Decay)
                diag_Decay(i,i) = 1./Decay(i);
            end
            MI_species = [];
            for i = active
                MI_species = [MI_species, PamMeta.fFCS.MI_Hist{u}{i}(valid)./sum(PamMeta.fFCS.MI_Hist{u}{i}(valid))]; % re-normalize here since not all bins are used!
            end
            filters_temp = ((MI_species'*diag_Decay*MI_species)^(-1)*MI_species'*diag_Decay)';
            % compute the reconstruction of the decay pattern based on species (used for evaluation of filter quality)
            reconstruction_temp = sum((MI_species'*diag_Decay*MI_species)^(-1)*MI_species',1);
            reconstruction{u} = zeros(numel(PamMeta.fFCS.Decay_Hist{u}),1);
            reconstruction{u}(valid) = reconstruction_temp;
            %%% rescale filters back to total microtime range (no cut with valid)
            filters = zeros(numel(PamMeta.fFCS.Decay_Hist{u}),numel(active));            
            for i = 1:numel(active)
                filters(valid,i) = filters_temp(:,i);
            end

reconstruction = reconstruction{u};

% --- BurstBrowser inputs bound to Calc_fFCS_Filters.m names ---
Decay_par = [];
for i = active
    Decay_par = [Decay_par, vertcat(MI_Hist{u}{i,:})];
end
BurstMeta.fFCS.hist_MItotal_par = vertcat(Decay_Hist{u}{:});

% --- Calc_fFCS_Filters.m 30-32 (verbatim) ---
Decay_par = Decay_par./repmat(sum(Decay_par,1),size(Decay_par,1),1);
Decay_total_par = BurstMeta.fFCS.hist_MItotal_par;
Decay_total_par(Decay_total_par == 0) = 1; %%% fill zeros with eps

% --- Calc_fFCS_Filters.m 54-58 (verbatim) ---
%%% calculate the diagonal over the Decay_total
diag_Decay_total_par = zeros(numel(Decay_total_par));
for i = 1:numel(Decay_total_par)
    diag_Decay_total_par(i,i) = 1/Decay_total_par(i);
end

% --- Calc_fFCS_Filters.m 65-67 (verbatim) ---
BurstMeta.fFCS.filters_par = (Decay_par'*diag_Decay_total_par*Decay_par)^(-1)*Decay_par'*diag_Decay_total_par;
BurstMeta.fFCS.reconstruction_par = sum((Decay_par'*diag_Decay_total_par*Decay_par)^(-1)*Decay_par',1);
BurstMeta.fFCS.weighted_residuals_par = (Decay_total_par'-BurstMeta.fFCS.reconstruction_par)./(sqrt(Decay_total_par'));

filters_bb = BurstMeta.fFCS.filters_par';
reconstruction_bb = BurstMeta.fFCS.reconstruction_par';
weighted_residuals_bb = BurstMeta.fFCS.weighted_residuals_par';
save('-v7', 'ab_output.mat', 'filters', 'reconstruction', 'filters_bb', 'reconstruction_bb', 'weighted_residuals_bb');
