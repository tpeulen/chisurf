// Line geometry: the `lines` and `ribbon` representations, and measurement
// dashes.
//
// Unlit on purpose. A line's vertex normal is whatever the builder happened to
// leave in the array -- there is no surface to orient -- so lighting it makes
// the wireframe flicker as the camera turns. It still takes the depth cue, or a
// wireframe floats in front of the molecule it belongs to.

struct VertexIn {
    @location(0) position : vec3<f32>,
    @location(1) colour   : vec4<f32>,
};

struct VertexOut {
    @builtin(position) clip : vec4<f32>,
    @location(0) colour     : vec4<f32>,
    @location(1) viewPos    : vec3<f32>,
};

@vertex
fn vs_main(in: VertexIn) -> VertexOut {
    var out : VertexOut;
    let world = vec4<f32>(in.position, 1.0);
    out.clip    = u.mvp * world;
    out.viewPos = (u.view * world).xyz;
    out.colour  = in.colour;
    return out;
}

@fragment
fn fs_main(in: VertexOut) -> @location(0) vec4<f32> {
    return shade_unlit(in.colour, in.viewPos);
}
