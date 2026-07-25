% A/B reference dump: run the unmodified PAM/MIA RICSPE kernels in Octave and
% write every intermediate to full-precision text for the Python side.
%
% Everything is copied from RICSPE.m verbatim (the scalar block) or calls the
% reference .m files unchanged. Written with %.17e -- `save -ascii` truncates to
% 8 digits, which is coarser than the differences being looked for.

% Point these at your PAM checkout and an output directory:
addpath('<PAM>/functions/MIA/RICSPE');
out = '.';

function dump(path, A)
  % Write a 2-D array at full double precision, one row per line.
  fid = fopen(path, 'w');
  for i = 1:rows(A)
    fprintf(fid, '%.17e ', A(i,:));
    fprintf(fid, '\n');
  end
  fclose(fid);
end

% --- settings (must match the Python side exactly) ---
D          = 10;
wr         = 0.25;
wz         = 1.25;
PixelSize  = 0.05;
NX         = 16;
NY         = 16;
Nparticles = 50;
Brightness = 1e5;
Tp         = 1e-5;
Tl         = 1e-3;
Nlags      = 3;

% --- RICSPE.m scalar block, verbatim ---
alpha = wz / wr;
gamma(1) = 1/(2*sqrt(2));
gamma(2) = gamma(1)/(2*sqrt(2));
gamma(3) = gamma(1)/(3*sqrt(3));
gamma(4) = gamma(1)/8;
V = ( NX * PixelSize + 2 ) * ( NY * PixelSize + 2 ) * ( (NX+NY)/2 * PixelSize );
omega = pi^(3/2)*wr^3*alpha;

M = Nparticles;
beta = 1/alpha^2;
tauc = wr^2/(4*D);
fact = ( 1 + beta * Tp / tauc ) ^ 0.5;
q = Brightness * 4 * tauc^2 * ( beta * ( 1 + Tp/tauc ) * atanh( (1-beta)^0.5 * ( fact - 1 ) / ( beta + fact - 1 ) ) - (1-beta)^0.5*( fact - 1 )  ) / ( Tp * beta * (1-beta)^0.5 );
Mapp = M * Brightness * Tp / q;
m = Mapp * omega / V;
F = Mapp*q*omega*gamma(1)/V;

dump(fullfile(out,'ref_scalars.txt'), [alpha V omega beta tauc fact q Mapp m F gamma(1) gamma(2) gamma(3) gamma(4)]);

% --- the ideal correlation grid (RICS_CorrFun), verbatim ---
[ X, Y ] = meshgrid ( 0 : Nlags, 0 : Nlags );
Coeff = ones( Nlags+1, Nlags+1, 4 );
Coeff(:,:,1) = - ( ( PixelSize*X' ).^2 + ( PixelSize*Y' ).^2 ) / wr^2;
Coeff(:,:,2) = 4 * abs( Tp*X'  + Tl*Y' ) / wr^2;
Coeff(:,:,3) = 4 * abs( Tp*X'  + Tl*Y' ) / wz^2;
Coeff(1,1,4) = 0;
giD0 = RICS_CorrFun([D (1/m) 0], Coeff);
dump(fullfile(out,'ref_giD0.txt'), giD0);

% --- the three-point correlation over a spread of lag triples ---
% rows: [r1x r1y r2x r2y r3x r3y value]
trip = [];
for a = 0:Nlags
  for b = 0:Nlags
    trip(end+1,:) = [a b 0 0 a b g3([a b],[0 0],[a b],D,wr,alpha,Tp,Tl,PixelSize)];
  end
end
asym = [0 1 0 0 1 1; 1 0 2 0 0 1; 2 2 1 0 1 1; 0 1 1 0 3 2; 1 2 0 1 2 0; 3 1 1 1 0 2];
for k = 1:rows(asym)
  r1 = asym(k,1:2); r2 = asym(k,3:4); r3 = asym(k,5:6);
  trip(end+1,:) = [r1 r2 r3 g3(r1,r2,r3,D,wr,alpha,Tp,Tl,PixelSize)];
end
dump(fullfile(out,'ref_g3.txt'), trip);

% --- the full estimator covariance ---
tic;
Covariance = res_covariance( Nlags , NX , NY , D , F , wr, alpha , Tp , Tl , PixelSize, m , q , gamma );
t_cov = toc;
dump(fullfile(out,'ref_cov.txt'), Covariance);

% --- the three terms separately, for one representative entry each ---
% Re-runs the res_covariance body for a handful of (chi,psi,nu,mu) so a
% mismatch can be localised to term1 (shot/g3), term2 or term3.
probes = [0 0 0 1; 1 0 1 0; 1 1 1 1; 0 1 2 1; 2 0 3 1; 1 2 1 2];
terms = [];
for k = 1:rows(probes)
  chi = probes(k,1); psi = probes(k,2); nu = probes(k,3); mu = probes(k,4);

  term1 = 0;
  if ( nu == chi && mu == psi )
    term1 = 2*(NX-2*chi)*(NY-2*psi)*( m*q^4*gamma(4)* g3( [chi psi] , [0 0] , [chi psi] , D , wr, alpha , Tp , Tl , PixelSize ) );
  end

  x = (1-NX+chi):(NX-chi-1);
  y = (1-NY+psi):(NY-psi-1);
  [X,Y] = meshgrid(x,y);

  function g = g1grid(rx, ry, D, wr, alpha, Tp, Tl, PixelSize, m, q, gamma)
    c1 = - ( ( PixelSize*rx ).^2 + ( PixelSize*ry ).^2 ) / wr^2;
    c2 = 4 * ( abs(Tp*rx + Tl*ry) ) / wr^2;
    c3 = 4 * ( abs(Tp*rx + Tl*ry) ) / (alpha*wr)^2;
    g = m*q^2*gamma(2) .* (1./(1+D*c2)./sqrt(1+D*c3) .* exp(c1./(1+D*c2)));
  end

  g1v1 = g1grid(X, Y, D,wr,alpha,Tp,Tl,PixelSize,m,q,gamma);
  g1v1( ceil(numel(y)/2) , ceil(numel(x)/2) ) = g1v1( ceil(numel(y)/2) , ceil(numel(x)/2) ) + m*q*gamma(1);

  [~, Xtmp] = meshgrid(1:(NX-chi),1:(NX-chi));
  tmpx = Xtmp-Xtmp'; tmpx = tmpx(:);
  countx = sum(tmpx==unique(tmpx)');
  [~, Ytmp] = meshgrid(1:(NY-psi),1:(NY-psi));
  tmpy = Ytmp-Ytmp'; tmpy = tmpy(:);
  county = sum(tmpy==unique(tmpy)');
  count = county' * countx;

  g1v2 = g1grid(X+nu-chi, Y+mu-psi, D,wr,alpha,Tp,Tl,PixelSize,m,q,gamma);
  g1v2( g1v2 == max(g1v2(:)) ) = g1v2( g1v2 == max(g1v2(:)) ) + m*q*gamma(1);
  term2 = sum(sum( count .* ( g1v1 .* g1v2 ) ));

  g2v1 = g1grid(X+nu, Y+mu, D,wr,alpha,Tp,Tl,PixelSize,m,q,gamma);
  g2v1( g2v1 == max(g2v1(:)) ) = g2v1( g2v1 == max(g2v1(:)) ) + m*q*gamma(1);
  g2v2 = g1grid(X-chi, Y-psi, D,wr,alpha,Tp,Tl,PixelSize,m,q,gamma);
  g2v2( g2v2 == max(g2v2(:)) ) = g2v2( g2v2 == max(g2v2(:)) ) + m*q*gamma(1);
  term3 = sum(sum( count .* g2v1 .* g2v2 ));

  % where did the shot term actually land, and was the max unique?
  [~, imax] = max(g1v2(:));
  [iy, ix] = ind2sub(size(g1v2), imax);
  nmax = sum(g1v2(:) == max(g1v2(:)));
  terms(end+1,:) = [chi psi nu mu term1 term2 term3 ix iy nmax];
end
dump(fullfile(out,'ref_terms.txt'), terms);

SPD = nearestSPD(Covariance(2:end,2:end));
dump(fullfile(out,'ref_spd.txt'), SPD);

printf('octave: covariance %dx%d in %.1f s\n', rows(Covariance), columns(Covariance), t_cov);
