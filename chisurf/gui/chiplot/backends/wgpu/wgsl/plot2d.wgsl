// 2-D plot primitives for the chiplot WebGPU backend.
//
// Everything a plot draws arrives here already in clip space: the canvas maps
// data -> NDC on the CPU (it has to anyway, for the log axes and the pixel-space
// line widths), so there is no transform uniform and no per-batch bind group on
// the solid path. That keeps a frame to one buffer write per batch.
//
// Two entry pairs:
//   vs_solid / fs_solid  -- per-vertex RGBA, used by every filled and stroked
//                           primitive (lines are expanded to triangles on the
//                           CPU because WebGPU has no line width).
//   vs_image / fs_image  -- a textured quad for heatmaps.

struct SolidOut {
    @builtin(position) clip_pos: vec4<f32>,
    @location(0) color: vec4<f32>,
};

@vertex
fn vs_solid(
    @location(0) pos: vec2<f32>,
    @location(1) color: vec4<f32>,
) -> SolidOut {
    var out: SolidOut;
    out.clip_pos = vec4<f32>(pos, 0.0, 1.0);
    out.color = color;
    return out;
}

@fragment
fn fs_solid(in: SolidOut) -> @location(0) vec4<f32> {
    return in.color;
}

struct ImageOut {
    @builtin(position) clip_pos: vec4<f32>,
    @location(0) uv: vec2<f32>,
};

@group(0) @binding(0) var img_texture: texture_2d<f32>;
@group(0) @binding(1) var img_sampler: sampler;

@vertex
fn vs_image(
    @location(0) pos: vec2<f32>,
    @location(1) uv: vec2<f32>,
) -> ImageOut {
    var out: ImageOut;
    out.clip_pos = vec4<f32>(pos, 0.0, 1.0);
    out.uv = uv;
    return out;
}

@fragment
fn fs_image(in: ImageOut) -> @location(0) vec4<f32> {
    // The colour map is applied on the CPU, so the texture already holds the
    // final RGBA. Sampling it straight through keeps one code path for
    // "mapped scalar field" and "RGBA image the caller supplied".
    return textureSample(img_texture, img_sampler, in.uv);
}
