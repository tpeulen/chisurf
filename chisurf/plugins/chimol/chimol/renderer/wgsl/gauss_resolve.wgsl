// Turn the accumulated Gaussian field into a lit surface, one fullscreen pass.
//
// `gauss_splat.wgsl` leaves an offscreen RGBA target holding the
// density-weighted colour sum in `rgb` and the density in `a`. This reads it,
// cuts at the iso level, and shades what is left.
//
// The normal is the field's own gradient
// --------------------------------------
// A meshed surface carries a normal per vertex, computed from the analytic
// density gradient. Here there are no vertices, so the normal comes from the
// *screen-space* gradient of the accumulated density -- central differences on
// the four neighbouring texels, with `z` fixed at one and the whole thing
// normalised. That is exact for a height field and an approximation for a
// surface in perspective, and the approximation is invisible at the scale a
// molecular surface is looked at: what it gets wrong is the shading of a
// silhouette seen edge-on, where the true normal is perpendicular to the view
// and this one leans toward the camera.
//
// It also has one real virtue over a mesh normal: it costs four texture reads
// and no geometry, so the surface stays smooth however far the camera zooms in.
// A mesh at a 0.5 A grid spacing shows its facets by then.
//
// The shading goes through the shared `shade()`
// ---------------------------------------------
// Not a private Blinn-Phong. chimol's light rig is a *setting* -- key, fill,
// ambient, specular, rim, and a depth cue measured over the scene -- and a
// surface lit by its own hardcoded rig is a surface that stops matching the
// cartoon beside it the moment anyone changes the lighting. That mismatch is
// exactly the bug this codebase already paid for once, when the WebGPU backend
// carried a `DEFAULT_LIGHTING` dict that matched none of the configured values.

@group(1) @binding(0) var densityTexture : texture_2d<f32>;
@group(1) @binding(1) var densitySampler : sampler;
//: The density-weighted view depth, accumulated alongside the field. Dividing
//: it by the density gives the depth of the surface at this pixel, and *that*
//: is the height field whose gradient is a normal worth shading.
@group(1) @binding(2) var depthTexture : texture_2d<f32>;

struct ResolveOut {
    @builtin(position) clip : vec4<f32>,
    @location(0) uv         : vec2<f32>,
};

@vertex
fn vs_main(@builtin(vertex_index) vertexIndex : u32) -> ResolveOut {
    // One triangle covering the screen, derived from the index: no vertex
    // buffer, no index buffer, and no seam down the diagonal of a two-triangle
    // quad.
    let uv = vec2<f32>(
        f32((vertexIndex << 1u) & 2u),
        f32(vertexIndex & 2u),
    );
    var out : ResolveOut;
    out.clip = vec4<f32>(uv * 2.0 - 1.0, 0.0, 1.0);
    // WebGPU's texture origin is the top left and clip space's is the bottom
    // left, so the sampling coordinate is flipped in y. Getting this wrong
    // renders the surface upside down over a molecule that is the right way up.
    out.uv = vec2<f32>(uv.x, 1.0 - uv.y);
    return out;
}

//: Depth of the surface at a sampling point: the weighted mean of the front
//: faces that reach it, or zero where nothing does.
fn surfaceDepth(uv: vec2<f32>) -> f32 {
    let density = textureSample(densityTexture, densitySampler, uv).a;
    if (density < 1e-4) {
        return 0.0;
    }
    // Un-normalised: the splat scaled the depth by `u.gauss.w` to fit a
    // blendable 16-bit target.
    return textureSample(depthTexture, densitySampler, uv).r
        / (density * max(u.gauss.w, 1e-9));
}

fn smoothSurfaceDepth(uv: vec2<f32>, texel: vec2<f32>) -> f32 {
    let c = surfaceDepth(uv);
    if (c < 1e-4) {
        return 0.0;
    }
    var sum = c * 4.0;
    var count = 4.0;
    let step_sz = 2.0;
    let dx = vec2<f32>(texel.x * step_sz, 0.0);
    let dy = vec2<f32>(0.0, texel.y * step_sz);

    let r = surfaceDepth(uv + dx); if (r > 1e-4) { sum += r; count += 1.0; }
    let l = surfaceDepth(uv - dx); if (l > 1e-4) { sum += l; count += 1.0; }
    let d = surfaceDepth(uv + dy); if (d > 1e-4) { sum += d; count += 1.0; }
    let u_d = surfaceDepth(uv - dy); if (u_d > 1e-4) { sum += u_d; count += 1.0; }

    return sum / count;
}

struct ResolveFragmentOutput {
    @location(0) colour : vec4<f32>,
    @builtin(frag_depth) depth : f32,
};

@fragment
fn fs_main(in: ResolveOut) -> ResolveFragmentOutput {
    let field = textureSample(densityTexture, densitySampler, in.uv);
    let density = field.a;
    let iso = u.gauss.y;
    if (density < iso) {
        discard;
    }

    let texel = vec2<f32>(1.0) / vec2<f32>(textureDimensions(densityTexture));
    let centre = surfaceDepth(in.uv);
    let step_sz = 2.5;
    let right = smoothSurfaceDepth(in.uv + vec2<f32>(texel.x * step_sz, 0.0), texel);
    let left  = smoothSurfaceDepth(in.uv - vec2<f32>(texel.x * step_sz, 0.0), texel);
    let down  = smoothSurfaceDepth(in.uv + vec2<f32>(0.0, texel.y * step_sz), texel);
    let up    = smoothSurfaceDepth(in.uv - vec2<f32>(0.0, texel.y * step_sz), texel);

    // Central differences of the *depth*, converted from "per texel" to "per
    // view unit" by the pixel size at this depth.
    let perPixel = max(centre, 1e-3) / max(u.flags.z, 1e-6);
    let dzdx = (right - left) * 0.5 / (step_sz * max(perPixel, 1e-6));
    let dzdy = (down - up) * 0.5 / (step_sz * max(perPixel, 1e-6));

    // Depth grows away from the camera, so the outward normal takes the
    // gradient's sign on x and its negation on y -- the sampling coordinate is
    // already flipped in y by the vertex stage.
    var normal = normalize(vec3<f32>(dzdx, -dzdy, -1.0));
    // A pixel whose neighbours are all outside the surface has no gradient to
    // speak of; facing the camera is the honest answer there and it keeps the
    // rim from flashing.
    if (!(dot(normal, normal) > 0.5)) {
        normal = vec3<f32>(0.0, 0.0, 1.0);
    }

    var s : Surface;
    // The weighted mean colour: the splat pass accumulated colour premultiplied
    // by density, so this is the average of the atoms that reach this pixel.
    s.colour = vec4<f32>(field.rgb / max(density, 1e-6), u.gauss.z);
    s.normal = -normal;
    let ndc_x = in.uv.x * 2.0 - 1.0;
    let ndc_y = 1.0 - in.uv.y * 2.0;
    let view_x = ndc_x * centre / max(u.proj[0][0], 1e-6);
    let view_y = ndc_y * centre / max(u.proj[1][1], 1e-6);
    let view_pos = vec3<f32>(view_x, view_y, -centre);

    s.viewPos = view_pos;

    // Screen-space crevice ambient occlusion: compare center depth against surrounding depths
    var ao_sum = 0.0;
    let ao_step = 3.0;
    let r_ao = surfaceDepth(in.uv + vec2<f32>(texel.x * ao_step, 0.0));
    let l_ao = surfaceDepth(in.uv - vec2<f32>(texel.x * ao_step, 0.0));
    let d_ao = surfaceDepth(in.uv + vec2<f32>(0.0, texel.y * ao_step));
    let u_ao = surfaceDepth(in.uv - vec2<f32>(0.0, texel.y * ao_step));
    if (r_ao > 1e-4) { ao_sum += max(0.0, centre - r_ao); }
    if (l_ao > 1e-4) { ao_sum += max(0.0, centre - l_ao); }
    if (d_ao > 1e-4) { ao_sum += max(0.0, centre - d_ao); }
    if (u_ao > 1e-4) { ao_sum += max(0.0, centre - u_ao); }
    s.occlusion = clamp(ao_sum * 0.15 / max(perPixel, 1e-3), 0.0, 0.6);

    var out : ResolveFragmentOutput;
    out.colour = shade(s, true);
    let clip_p = u.proj * vec4<f32>(view_pos, 1.0);
    out.depth = clamp(clip_p.z / max(clip_p.w, 1e-6), 0.0, 1.0);
    return out;
}
