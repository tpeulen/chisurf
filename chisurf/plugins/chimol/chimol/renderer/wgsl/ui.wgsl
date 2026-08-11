// The in-viewport chrome, as quads.
//
// Why this replaces a full-viewport texture
// -----------------------------------------
// The panel, the sequence strip, the menus and the transport used to be
// rasterised on the CPU into an image the size of the window and uploaded every
// time it changed -- `9.6 ms of a 21 ms frame` on a quarter-million beads, which
// is why a timer existed to let the panel go deliberately *stale* rather than
// repaint it when it changed. A frame of chrome is a few hundred rectangles and
// a few thousand glyphs; sending those as vertices costs kilobytes and no CPU
// rasterisation at all.
//
// One pipeline draws both. A rectangle samples the atlas's opaque block, so
// there is no "is this text" branch and no second pipeline -- the difference
// between a panel background and a letter is which texels the quad points at.
//
// Clipping travels per-vertex rather than as a scissor rect, because the whole
// chrome is one draw call and a scissor would split it. Menus are the only
// caller, and a menu taller than its box scrolls inside it.
//
// Output is **premultiplied**, matching the blend state the chrome has always
// been composited with. Straight alpha here darkens every antialiased glyph
// edge against a light background -- which is invisible on the dark panel and
// obvious the moment the background is white.

struct UiOut {
    @builtin(position) clip   : vec4<f32>,
    @location(0) uv           : vec2<f32>,
    @location(1) colour       : vec4<f32>,
    // The clip rectangle, in pixels: (x0, y0, x1, y1).
    @location(2) box          : vec4<f32>,
    // Where this fragment is, in the same pixel space, so the fragment stage
    // can test it against `box` without recovering it from `clip`.
    @location(3) pixel        : vec2<f32>,
};

struct UiUniforms {
    // Viewport size in pixels, and the atlas size in texels.
    viewport : vec2<f32>,
    atlas    : vec2<f32>,
};

@group(1) @binding(0) var<uniform> ui : UiUniforms;
@group(1) @binding(1) var uiTex : texture_2d<f32>;
@group(1) @binding(2) var uiSampler : sampler;

@vertex
fn vs_ui(
    @location(0) position : vec2<f32>,
    @location(1) uv       : vec2<f32>,
    @location(2) colour   : vec4<f32>,
    @location(3) box      : vec4<f32>,
) -> UiOut {
    var out : UiOut;
    // Pixels to clip space. The chrome lays itself out y-down from the top
    // left, as every 2-D layout does; clip space is y-up.
    let ndc = vec2<f32>(
         position.x / ui.viewport.x * 2.0 - 1.0,
         1.0 - position.y / ui.viewport.y * 2.0,
    );
    out.clip = vec4<f32>(ndc, 0.0, 1.0);
    out.uv = uv / ui.atlas;
    out.colour = colour;
    out.box = box;
    out.pixel = position;
    return out;
}

@fragment
fn fs_ui(in: UiOut) -> @location(0) vec4<f32> {
    if (in.pixel.x < in.box.x || in.pixel.x > in.box.z ||
        in.pixel.y < in.box.y || in.pixel.y > in.box.w) {
        discard;
    }
    // The atlas stores coverage in alpha; its colour channels are white where
    // there is ink, so sampling alpha alone is what carries the glyph and lets
    // the vertex colour decide what it looks like.
    let coverage = textureSample(uiTex, uiSampler, in.uv).a;
    let alpha = in.colour.a * coverage;
    return vec4<f32>(in.colour.rgb * alpha, alpha);
}
