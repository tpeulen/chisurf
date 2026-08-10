// The depth-discontinuity outline, transcribed from the OpenGL post-pass.
//
// An outline drawn from *depth* rather than from geometry: a fragment whose
// nearest neighbour within the brush radius is much closer than itself sits on
// a silhouette, whatever drew it. That is why it costs nothing per object and
// works identically on a cartoon, a surface and an impostor sphere -- including
// the impostors, whose silhouette is not in any triangle and which an edge
// detector over geometry would miss entirely.
//
// The `jump` comparison **linearises** the depth buffer, so `depth_jump` stays
// a fraction of scene depth instead of meaning something different at every
// distance. That form is the GL original's and is kept exactly: an outline that
// thickens as the camera pulls back is the classic sign of comparing raw
// non-linear depth.

struct Outline {
    // x depth_jump, y near/far ratio, z thickness in pixels, w unused
    params : vec4<f32>,
    colour : vec4<f32>,
    // x 1/width, y 1/height
    texel  : vec4<f32>,
};

@group(0) @binding(0) var<uniform> o : Outline;
@group(1) @binding(0) var depthTex : texture_depth_2d;
@group(1) @binding(1) var depthSampler : sampler;

struct OutlineOut {
    @builtin(position) clip : vec4<f32>,
    @location(0) uv         : vec2<f32>,
};

//: The brush radius is clamped so the inner loop is a compile-time constant and
//: the cost is predictable rather than scaling with a user setting.
const MAX_THICKNESS : i32 = 4;

@vertex
fn vs_outline(@builtin(vertex_index) vertexIndex : u32) -> OutlineOut {
    var corners = array<vec2<f32>, 6>(
        vec2<f32>(-1.0, -1.0), vec2<f32>( 1.0, -1.0), vec2<f32>( 1.0,  1.0),
        vec2<f32>(-1.0, -1.0), vec2<f32>( 1.0,  1.0), vec2<f32>(-1.0,  1.0),
    );
    let c = corners[vertexIndex];
    var out : OutlineOut;
    out.clip = vec4<f32>(c, 0.0, 1.0);
    out.uv = vec2<f32>(c.x * 0.5 + 0.5, 0.5 - c.y * 0.5);
    return out;
}

@fragment
fn fs_outline(in: OutlineOut) -> @location(0) vec4<f32> {
    let d0 = textureSample(depthTex, depthSampler, in.uv);
    var ds = d0;
    let thickness = o.params.z;
    let r2 = thickness * thickness;

    for (var i = -MAX_THICKNESS; i <= MAX_THICKNESS; i = i + 1) {
        for (var j = -MAX_THICKNESS; j <= MAX_THICKNESS; j = j + 1) {
            let fi = f32(i);
            let fj = f32(j);
            if (fi * fi + fj * fj <= r2 && !(i == 0 && j == 0)) {
                let uv = in.uv + vec2<f32>(fi * o.texel.x, fj * o.texel.y);
                ds = min(ds, textureSample(depthTex, depthSampler, uv));
            }
        }
    }

    let nf = o.params.y;
    let nf1 = 1.0 - nf;
    if (nf * (d0 - ds) < o.params.x * (1.0 - nf1 * ds) * (1.0 - nf1 * d0)) {
        discard;
    }
    return o.colour;
}
