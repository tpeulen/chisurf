// A molecular surface with no grid and no mesh: Gaussian splats in screen space.
//
// What this is for
// ----------------
// The meshed surface -- density grid, iso-threshold, distance transform,
// marching cubes -- is 253 ms for T4 lysozyme and produces 27,920 vertices that
// have to be rebuilt whenever an atom moves. That is the right answer when the
// deliverable is *geometry*: an OBJ to export, a volume to measure, a mesh to
// ray-trace. It is the wrong answer for turning a molecule with the mouse.
//
// So this is the interactive quality level. Each atom is one camera-facing quad
// carrying an isotropic Gaussian; the quads are blended **additively** into an
// offscreen target, and `gauss_resolve.wgsl` turns the accumulated field into a
// lit surface at the iso level. There is no 3-D grid to allocate, no mesh to
// build and nothing to rebuild when the molecule moves -- the field is
// evaluated in the pixels that show it, at the resolution that shows it.
//
// Four channels, not one
// ----------------------
// The obvious form accumulates a scalar density and shades it in one colour.
// A molecular surface is coloured by what is underneath it -- chain, element,
// b-factor, a spectrum -- so this accumulates **premultiplied colour** as well:
// `rgb` is the density-weighted colour sum and `a` is the density. The resolve
// divides one by the other, which is the same weighted mean the meshed path
// computes per vertex with `shade_from_atoms`, done per pixel instead.
//
// The blend state is `one, one` on both channels -- see `_gauss_pipelines` in
// `wgpu_backend.py`. Any other blend makes the sum depend on draw order, which
// for an unsorted instance buffer means the surface changes when the camera
// does.

//: The same per-instance layout the sphere impostors use -- centre, radius,
//: colour, occlusion -- so a scene object can be drawn either way without
//: repacking. See `WgpuMeshRenderer.interleave_impostors`.
struct InstanceIn {
    @location(0) sphere    : vec4<f32>,
    @location(1) colour    : vec4<f32>,
    @location(2) occlusion : f32,
};

struct SplatOut {
    @builtin(position) clip : vec4<f32>,
    @location(0) colour     : vec4<f32>,
    // Position within the quad, in [-1, 1]: the Gaussian is a function of this
    // alone, so the splat is the same size in pixels wherever it lands.
    @location(1) local      : vec2<f32>,
    // The atom's own depth in view space, so the resolve can reconstruct a
    // depth for the surface rather than drawing it flat.
    @location(2) @interpolate(flat) depthView : f32,
    @location(3) @interpolate(flat) radiusView : f32,
};

//: The atom's radius, in view units. A helper only so the fragment stage reads
//: as what it means.
fn inst_radius(in: SplatOut) -> f32 {
    return in.radiusView;
}

//: How far out the quad reaches, in multiples of the radius. The Gaussian is
//: not compactly supported, so this is where it is *cut*: at 2.5 sigma the
//: remaining density is under 1 % of the peak, which is below any iso level
//: worth drawing and keeps the quad small enough that overdraw stays bounded.
const CUTOFF : f32 = 2.5;

@vertex
fn vs_main(
    @builtin(vertex_index) vertexIndex : u32,
    inst: InstanceIn,
) -> SplatOut {
    var corners = array<vec2<f32>, 6>(
        vec2<f32>(-1.0, -1.0), vec2<f32>( 1.0, -1.0), vec2<f32>( 1.0,  1.0),
        vec2<f32>(-1.0, -1.0), vec2<f32>( 1.0,  1.0), vec2<f32>(-1.0,  1.0),
    );
    let corner = corners[vertexIndex];

    let centreView = (u.view * vec4<f32>(inst.sphere.xyz, 1.0)).xyz;
    let reach = inst.sphere.w * CUTOFF;

    var out : SplatOut;
    out.clip = u.proj * vec4<f32>(centreView + vec3<f32>(corner * reach, 0.0), 1.0);
    out.colour = inst.colour;
    out.local = corner;
    out.depthView = -centreView.z;
    out.radiusView = inst.sphere.w;
    return out;
}

//: Two attachments, not one. The second is what gives the surface its shape.
//:
//: A field alone has no depth: inside the molecule the density saturates, its
//: screen-space gradient goes to zero, and every interior pixel gets the same
//: normal -- a flat silhouette with a lit rim, which is what the first version
//: of this drew. Accumulating the density-weighted **view depth** as well gives
//: the resolve a height field to differentiate, and a height field is exactly
//: what a screen-space normal is correct for.
struct SplatTargets {
    @location(0) field : vec4<f32>,
    @location(1) depth : vec4<f32>,
};

@fragment
fn fs_main(in: SplatOut) -> SplatTargets {
    let r2 = dot(in.local, in.local);
    if (r2 > 1.0) {
        // The corners of the quad, outside the cutoff circle. Discarding them
        // is cheaper than blending zeros, and it keeps the overdraw honest.
        discard;
    }

    // `exp(-alpha * (r * CUTOFF)^2)`: `local` is normalised to the *cutoff*, so
    // the exponent is scaled back to sigma units here. `u.gauss.x` carries
    // alpha, the decay steepness -- 2 is a soft envelope, 5 hugs the atoms.
    let alpha = u.gauss.x;
    let density = exp(-alpha * r2 * CUTOFF * CUTOFF);

    // The near surface of the atom, not its centre: the splat stands for a
    // sphere, and what a viewer sees of a sphere is its front. Without the
    // offset the surface sits half a radius inside every atom and the shape
    // reads as a smoothed centroid cloud.
    let front = in.depthView - inst_radius(in) * sqrt(max(1.0 - r2, 0.0));

    var out : SplatTargets;
    // Premultiplied: the resolve divides both sums by the density, so an atom
    // contributes in proportion to how much of this pixel it owns.
    out.field = vec4<f32>(in.colour.rgb * density, density);
    // Normalised by `u.gauss.w` -- the target is 16-bit and blendable, and a
    // raw depth times a density of tens overflows it. The resolve scales back.
    out.depth = vec4<f32>(front * u.gauss.w * density, 0.0, 0.0, 0.0);
    return out;
}
