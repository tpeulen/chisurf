// Mesh shading, transcribed from the OpenGL backend's GLSL 120 fragment shader.
//
// This file is the *shared* source: the desktop backend compiles it through
// wgpu-py and a browser backend compiles the same text through WebGPU, so the
// two cannot drift. Where the GL original documents why a term is shaped the way
// it is -- PyMOL's fog being a linear visibility between two planes, the ambient
// and diffuse forming a convex mix, occlusion damping only the terms that do not
// come from the surface colour -- those reasons carry over unchanged and the
// comments are not repeated here; see `qtgl.py` until it is retired.
//
// One deliberate difference from GL: `occlusion` is already multiplied into
// `colour` by the scene builder, and is *also* passed separately so the terms
// that do not come from the surface (ambient, rim, environment) can be damped by
// it without counting it twice. The floor of 0.35 is the GL original's: damping
// linearly sent a deeply occluded fragment to black and swallowed whole helices.

struct Uniforms {
    mvp          : mat4x4<f32>,
    view         : mat4x4<f32>,
    normalMatrix : mat4x4<f32>,
    lightDir     : vec4<f32>,   // xyz used
    fillLightDir : vec4<f32>,
    fogColor     : vec4<f32>,   // rgb used, w = fogEnd
    // x key, y fill, z ambient, w specular
    intensities  : vec4<f32>,
    // x shininess, y rimStrength, z rimPower, w fogScale
    surface      : vec4<f32>,
    // x twoSided (0/1), y opacity, z unused, w unused
    flags        : vec4<f32>,
};
@group(0) @binding(0) var<uniform> u : Uniforms;

struct VertexIn {
    @location(0) position  : vec3<f32>,
    @location(1) normal    : vec3<f32>,
    @location(2) colour    : vec4<f32>,
    @location(3) occlusion : f32,
};

struct VertexOut {
    @builtin(position) clip : vec4<f32>,
    @location(0) colour     : vec4<f32>,
    @location(1) normal     : vec3<f32>,
    @location(2) viewPos    : vec3<f32>,
    @location(3) occlusion  : f32,
};

@vertex
fn vs_main(in: VertexIn) -> VertexOut {
    var out : VertexOut;
    let world = vec4<f32>(in.position, 1.0);
    out.clip      = u.mvp * world;
    out.colour    = in.colour;
    out.normal    = normalize((u.normalMatrix * vec4<f32>(in.normal, 0.0)).xyz);
    out.viewPos   = (u.view * world).xyz;
    out.occlusion = clamp(in.occlusion, 0.0, 1.0);
    return out;
}

@fragment
fn fs_main(in: VertexOut, @builtin(front_facing) frontFacing: bool) -> @location(0) vec4<f32> {
    var n = normalize(in.normal);
    // Two-sided lighting flips toward the *viewer*, not the light: flipping
    // toward the light darkens a front face lit only by the fill light, and the
    // point of the setting is to make the inside of a transparent shell visible.
    if (u.flags.x > 0.5 && !frontFacing) {
        n = -n;
    }

    let viewDir = normalize(-in.viewPos);
    let l       = normalize(u.lightDir.xyz);
    let lambert = max(dot(n, l), 0.0);
    let fillLam = max(dot(n, normalize(u.fillLightDir.xyz)), 0.0);

    var spec = 0.0;
    if (lambert > 0.0) {
        let r = reflect(-l, n);
        spec = pow(max(dot(viewDir, r), 0.0), u.surface.x) * u.intensities.w;
    }

    let baseColor = in.colour.rgb;
    let alpha     = in.colour.a * u.flags.y;
    // Floored, not linear: occlusion is already in `baseColor`, so damping these
    // by the same factor counts it twice and drives crevices to solid black.
    let exposure  = mix(0.35, 1.0, clamp(1.0 - in.occlusion, 0.0, 1.0));
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
    shaded += env * 0.10 * sheet * exposure;

    shaded += vec3<f32>(spec) * sheet;

    // PyMOL's fog is a linear *visibility* between two planes, not an
    // exponential in distance, so `fog_start` means the same here as it does in
    // the ray tracer and in PyMOL.
    let vis = clamp((u.fogColor.w + in.viewPos.z) * u.surface.w, 0.0, 1.0);
    let out = mix(u.fogColor.rgb, shaded, vis);
    return vec4<f32>(out, alpha);
}
