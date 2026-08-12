// The shading model, and the uniform block every pipeline shares.
//
// Prepended to each entry-point shader by `load_wgsl`, because WGSL has no
// `#include` and the alternative -- a copy of `shade()` in the mesh shader and
// another in the impostor shader -- is the exact failure this port keeps
// finding: a constant transcribed between two readers drifts, and the drift is
// invisible until someone renders the same scene both ways. A mesh sphere and
// an impostor sphere must be indistinguishable where they overlap, which is
// only true if one function shades both.
//
// Transcribed from the OpenGL backend's GLSL 120 fragment shader. Where the GL
// original documents why a term is shaped the way it is -- PyMOL's fog being a
// linear visibility between two planes, the ambient and diffuse forming a
// convex mix, occlusion damping only the terms that do not come from the
// surface colour -- those reasons carry over unchanged; see `qtgl.py` until it
// is retired.
//
// One deliberate difference from GL: `occlusion` is already multiplied into
// `colour` by the scene builder, and is *also* passed separately so the terms
// that do not come from the surface (ambient, rim, environment) can be damped
// by it without counting it twice. The floor of 0.35 is the GL original's:
// damping linearly sent a deeply occluded fragment to black and swallowed whole
// helices.

struct Uniforms {
    mvp          : mat4x4<f32>,
    view         : mat4x4<f32>,
    proj         : mat4x4<f32>,
    normalMatrix : mat4x4<f32>,
    lightDir     : vec4<f32>,   // xyz used
    fillLightDir : vec4<f32>,
    fogColor     : vec4<f32>,   // rgb used, w = fogEnd
    // x key, y fill, z ambient, w specular
    intensities  : vec4<f32>,
    // x shininess, y rimStrength, z rimPower, w fogScale
    surface      : vec4<f32>,
    // x twoSided (0/1), y opacity, z pointScale (pixels per world unit at unit
    // depth), w worldRadius (0/1 -- whether an impostor's radius is a distance
    // in the model or a count of pixels)
    flags        : vec4<f32>,
    // The screen-space Gaussian surface: x decay steepness (alpha), y the iso
    // level the resolve cuts at, z the field's own opacity, w unused. Part of
    // the shared block rather than a second one because every pipeline binds
    // this block already -- a second uniform for two shaders is a second bind
    // group layout for all of them.
    gauss        : vec4<f32>,
};
@group(0) @binding(0) var<uniform> u : Uniforms;

//: What every pipeline hands the fragment stage. Impostors fill it from a
//: ray-sphere intersection rather than from interpolated vertex attributes,
//: which is the whole of their difference -- the shading downstream is identical.
struct Surface {
    colour    : vec4<f32>,
    normal    : vec3<f32>,
    viewPos   : vec3<f32>,
    occlusion : f32,
};

fn shade(s: Surface, frontFacing: bool) -> vec4<f32> {
    // Volume-image slices are emission, not a surface: no lighting, no rim, no
    // reflection, no transparency curve -- their per-vertex alpha *is* the
    // transfer function and reshaping it would change what the data says. Only
    // the depth cue still applies, so a slab deep in a big scene fades like
    // everything else. The flag rides in `u.gauss.w` because the slot was
    // spare and every pipeline already binds this block.
    if (u.gauss.w > 0.5) {
        var vis_unlit = 1.0;
        if (u.surface.w > 0.0) {
            vis_unlit = clamp((u.fogColor.w + s.viewPos.z) * u.surface.w, 0.0, 1.0);
        }
        let col = mix(u.fogColor.rgb, s.colour.rgb, vis_unlit);
        return vec4<f32>(col, s.colour.a * u.flags.y);
    }

    var n = normalize(s.normal);
    // Two-sided lighting flips toward the *viewer*, not the light: flipping
    // toward the light darkens a front face lit only by the fill light, and the
    // point of the setting is to make the inside of a transparent shell visible.
    if (u.flags.x > 0.5 && !frontFacing) {
        n = -n;
    }

    let viewDir = normalize(-s.viewPos);
    let l       = normalize(u.lightDir.xyz);
    let lambert = max(dot(n, l), 0.0);
    let fillLam = max(dot(n, normalize(u.fillLightDir.xyz)), 0.0);

    var spec = 0.0;
    if (lambert > 0.0) {
        let r = reflect(-l, n);
        spec = pow(max(dot(viewDir, r), 0.0), u.surface.x) * u.intensities.w;
    }

    let baseColor = s.colour.rgb;
    let alpha     = s.colour.a * u.flags.y;
    // Floored, not linear: occlusion is already in `baseColor`, so damping these
    // by the same factor counts it twice and drives crevices to solid black.
    let exposure  = mix(0.35, 1.0, clamp(1.0 - s.occlusion, 0.0, 1.0));
    // A translucent sheet is not a mirror. Reflection, rim and specular are
    // surface effects, and a stack of sheets accumulates white until a coloured
    // jelly reads as milk.
    let sheet     = mix(0.3, 1.0, clamp(alpha, 0.0, 1.0));

    let ambientCoeff = clamp(u.intensities.z, 0.0, 1.0);
    let litWeight    = clamp(u.intensities.x * lambert + u.intensities.y * fillLam, 0.0, 1.0);
    let ambient      = ambientCoeff * 0.7 * exposure;
    let diffuse      = (1.0 - ambient) * litWeight;
    var shaded       = baseColor * (ambient + diffuse);

    let rim = pow(clamp(1.0 - dot(n, viewDir), 0.0, 1.0), u.surface.z);
    shaded += baseColor * rim * u.surface.y * exposure * sheet;

    // Procedural environment reflection (a fake matcap), as in GL.
    let R         = reflect(-viewDir, n);
    let skyCol    = vec3<f32>(0.5, 0.7, 1.0);
    let groundCol = vec3<f32>(0.05, 0.05, 0.1);
    var env       = mix(groundCol, skyCol, smoothstep(-0.2, 0.4, R.y));
    let sunDir    = normalize(vec3<f32>(0.5, 1.0, 0.5));
    let sun       = pow(max(0.0, dot(R, sunDir)), max(10.0, u.surface.x));
    env += vec3<f32>(1.5) * sun;

    // Blended by Fresnel and *mixed*, not added at a flat fraction. Face-on the
    // reflection is barely there and at grazing angles it takes over, which is
    // what makes a ribbon read as a solid with an edge rather than as a shape
    // with a uniform sheen laid over it. Adding a constant 10 % instead lifts
    // the whole surface by the same amount, which is exactly what a flat
    // fraction cannot distinguish from raising the ambient term.
    let fresnel    = pow(clamp(1.0 - dot(n, viewDir), 0.0, 1.0), 2.5);
    let reflectMul = clamp(u.intensities.w * (0.1 + 0.6 * fresnel), 0.0, 1.0)
                     * exposure * sheet;
    var finalColor = mix(shaded, env, reflectMul);

    finalColor += vec3<f32>(spec) * exposure * sheet;

    // PyMOL's fog is a linear *visibility* between two planes, not an
    // exponential in distance, so `fog_start` means the same here as it does in
    // the ray tracer and in PyMOL. `viewPos.z` is negative in front of the
    // camera, so `fogEnd + z` is how far short of the back plane this fragment
    // is. A scale of 0 is how the host says the cue is off -- the same signal
    // the GL shader tests, so neither backend needs a sentinel distance.
    var vis = 1.0;
    if (u.surface.w > 0.0) {
        vis = clamp((u.fogColor.w + s.viewPos.z) * u.surface.w, 0.0, 1.0);
    }
    let out = mix(u.fogColor.rgb, finalColor, vis);

    // Transparency is a *curve*, not the alpha the caller asked for. The edge of
    // a jelly is more opaque than its middle, and the boost stays proportional
    // to the alpha asked for: a flat addition at the edges saturates a metaball,
    // which is nearly all edge, so 0.3 and 0.6 render indistinguishably and the
    // knob stops working. Passing the alpha straight through instead -- which is
    // what this shader did -- makes a surface at `transparency 0.5` render
    // almost solid, because face-on the curve is 0.55 of it.
    var finalAlpha = alpha;
    if (finalAlpha < 0.99) {
        let a = finalAlpha;
        finalAlpha = mix(a * 0.55, a + (1.0 - a) * 0.55, fresnel);
    }
    // Highlights are opaque -- a glint on wet glass hides what is behind it --
    // but scaled by the room left, or a glossy material simply is not
    // transparent. `spec` and `sun` are radiance terms and are not bounded by 1;
    // feeding them in unclamped drove a nominally 0.35-opaque surface to ~0.85.
    let glint = clamp(spec + sun, 0.0, 1.0) * 0.25 * (1.0 - finalAlpha);
    return vec4<f32>(out, clamp(finalAlpha + glint, 0.0, 1.0));
}

//: Flat colour with the depth cue applied, for geometry that has no surface to
//: light: lines, and the dot glyphs. Lighting a line by an interpolated normal
//: is worse than not lighting it -- the normal is whatever the builder left in
//: the array -- but a line still has to sit in the same fog as everything else,
//: or a wireframe floats in front of the molecule it belongs to.
fn shade_unlit(colour: vec4<f32>, viewPos: vec3<f32>) -> vec4<f32> {
    var vis = 1.0;
    if (u.surface.w > 0.0) {
        vis = clamp((u.fogColor.w + viewPos.z) * u.surface.w, 0.0, 1.0);
    }
    let alpha = colour.a * u.flags.y;
    return vec4<f32>(mix(u.fogColor.rgb, colour.rgb, vis), alpha);
}
