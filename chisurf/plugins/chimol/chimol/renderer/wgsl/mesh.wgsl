// Triangle meshes: cartoon ribbons, surfaces, sticks and tessellated spheres.
//
// Prefixed with `shading.wgsl`, which holds the uniform block and `shade()`.
// This file is only the plumbing from vertex attributes into a `Surface`.

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
    var s : Surface;
    s.colour    = in.colour;
    s.normal    = in.normal;
    s.viewPos   = in.viewPos;
    s.occlusion = in.occlusion;
    return shade(s, frontFacing);
}
