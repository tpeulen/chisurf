// Instanced 2-D sprite / signed-distance shape shader for chigame.
//
// One draw call renders every quad in a frame. Each instance carries its own
// position, size, colour and shape, so the default look needs no image files:
// terrain, creatures and UI are all signed-distance shapes evaluated here.
//
// An asset pack that ships a sprite atlas uses SHAPE_GLYPH with its own uv
// rectangle, so a textured pack and the procedural pack share this one shader.

const SHAPE_RECT:    f32 = 0.0;
const SHAPE_ELLIPSE: f32 = 1.0;
const SHAPE_ROUND:   f32 = 2.0;
const SHAPE_RING:    f32 = 3.0;
const SHAPE_GLYPH:   f32 = 4.0;
const SHAPE_GLOW:    f32 = 5.0;
const SHAPE_TRI:     f32 = 6.0;

struct Camera {
    // World-space point at the centre of the view.
    center: vec2<f32>,
    // Half the world-space width and height the view spans.
    half_extent: vec2<f32>,
};

struct Instance {
    // Centre of the quad, in world units.
    pos: vec2<f32>,
    // Full width and height, in world units.
    size: vec2<f32>,
    // Straight (non-premultiplied) sRGB colour.
    color: vec4<f32>,
    // x: shape id, y: shape parameter, z: rotation in radians, w: softness.
    params: vec4<f32>,
    // Atlas rectangle (u0, v0, u1, v1); only read by SHAPE_GLYPH.
    uv: vec4<f32>,
};

@group(0) @binding(0) var<uniform> camera: Camera;
@group(0) @binding(1) var<storage, read> instances: array<Instance>;
@group(0) @binding(2) var atlas: texture_2d<f32>;
@group(0) @binding(3) var atlas_sampler: sampler;

struct VertexOut {
    @builtin(position) clip: vec4<f32>,
    // Position within the quad, in [-1, 1] on both axes.
    @location(0) local: vec2<f32>,
    @location(1) color: vec4<f32>,
    @location(2) params: vec4<f32>,
    @location(3) uv: vec2<f32>,
    // Aspect ratio of the quad, needed so rounded corners stay circular.
    @location(4) aspect: vec2<f32>,
};

// The unit quad, as two triangles. Generated rather than supplied, so there is
// no vertex buffer to bind and no geometry to upload.
fn corner(index: u32) -> vec2<f32> {
    var corners = array<vec2<f32>, 6>(
        vec2<f32>(-1.0, -1.0), vec2<f32>( 1.0, -1.0), vec2<f32>(-1.0,  1.0),
        vec2<f32>(-1.0,  1.0), vec2<f32>( 1.0, -1.0), vec2<f32>( 1.0,  1.0),
    );
    return corners[index];
}

@vertex
fn vs_main(
    @builtin(vertex_index) vertex_index: u32,
    @builtin(instance_index) instance_index: u32,
) -> VertexOut {
    let inst = instances[instance_index];
    let local = corner(vertex_index);

    // Rotate in the quad's own frame, then scale, then translate.
    let angle = inst.params.z;
    let c = cos(angle);
    let s = sin(angle);
    let scaled = local * inst.size * 0.5;
    let rotated = vec2<f32>(scaled.x * c - scaled.y * s, scaled.x * s + scaled.y * c);
    let world = inst.pos + rotated;

    // World to normalised device coordinates. Y is flipped so that world-space
    // Y grows downward, which is what a tile map wants.
    let ndc = (world - camera.center) / camera.half_extent;

    var out: VertexOut;
    out.clip = vec4<f32>(ndc.x, -ndc.y, 0.0, 1.0);
    out.local = local;
    out.color = inst.color;
    out.params = inst.params;
    out.uv = mix(inst.uv.xy, inst.uv.zw, (local + 1.0) * 0.5);
    let longest = max(inst.size.x, max(inst.size.y, 1e-6));
    out.aspect = inst.size / longest;
    return out;
}

// Rounded-box signed distance, evaluated in the quad's local frame.
fn sd_round_box(p: vec2<f32>, half_size: vec2<f32>, radius: f32) -> f32 {
    let q = abs(p) - half_size + radius;
    return length(max(q, vec2<f32>(0.0))) + min(max(q.x, q.y), 0.0) - radius;
}

fn srgb_to_linear(c: vec3<f32>) -> vec3<f32> {
    let lo = c / 12.92;
    let hi = pow((c + 0.055) / 1.055, vec3<f32>(2.4));
    return select(hi, lo, c <= vec3<f32>(0.04045));
}

@fragment
fn fs_main(in: VertexOut) -> @location(0) vec4<f32> {
    let shape = in.params.x;
    let param = in.params.y;
    // Softness is expressed in local units so that an edge stays comparably
    // soft whatever the quad's size on screen.
    let softness = max(in.params.w, 1e-4);

    var alpha = 1.0;
    var rgb = in.color.rgb;

    if (shape == SHAPE_ELLIPSE) {
        alpha = 1.0 - smoothstep(1.0 - softness, 1.0, length(in.local));
    } else if (shape == SHAPE_ROUND) {
        // The radius is a fraction of the *shorter* half-extent, so param=1 is a
        // stadium and never exceeds the quad. Scaling it against the longer axis
        // instead makes a wide panel's corners bulge into ellipses.
        let half = in.aspect;
        let radius = clamp(param, 0.0, 1.0) * min(half.x, half.y);
        let d = sd_round_box(in.local * half, half, radius);
        alpha = 1.0 - smoothstep(-softness, 0.0, d);
    } else if (shape == SHAPE_RING) {
        let r = length(in.local);
        let inner = clamp(param, 0.0, 0.999);
        alpha = smoothstep(inner - softness, inner, r) *
                (1.0 - smoothstep(1.0 - softness, 1.0, r));
    } else if (shape == SHAPE_GLYPH) {
        // The atlas is coverage-only, so the instance colour tints it.
        alpha = textureSample(atlas, atlas_sampler, in.uv).r;
    } else if (shape == SHAPE_GLOW) {
        // Emission halo: bright core falling off to nothing at the rim. This is
        // what gives a fluorophore its look without any texture.
        let r = clamp(length(in.local), 0.0, 1.0);
        let falloff = pow(1.0 - r, max(param, 0.001) * 4.0);
        alpha = falloff;
        rgb = rgb * (1.0 + falloff * 0.6);
    } else if (shape == SHAPE_TRI) {
        // Upward triangle: apex at the top edge, base along the bottom. World Y
        // grows downward, so the apex is at local y = -1 and the half-width
        // grows linearly to 1 at the base.
        let t = (in.local.y + 1.0) * 0.5;
        alpha = 1.0 - smoothstep(t - softness, t + softness, abs(in.local.x));
    }

    let a = alpha * in.color.a;
    if (a <= 0.001) {
        discard;
    }
    return vec4<f32>(srgb_to_linear(clamp(rgb, vec3<f32>(0.0), vec3<f32>(1.0))), a);
}
