// Screen-space chrome: the object panel, the sequence strip, labels.
//
// Why this is a textured quad and not a Qt child widget
// -----------------------------------------------------
// The chrome paints with a `QPainter` and always did; `qtgl` opens one on its
// own `QOpenGLWidget` after the GL pass. A WebGPU surface cannot take that: it
// is presented by the compositor, and a translucent child stacked over it does
// not blend with it -- it *covers* it. Measured both ways: without clearing the
// child's backing store the molecule came back salmon-and-blue (uncleared
// memory composited over the frame, which reads exactly like a channel-order
// bug and is not one); with the clear, the molecule disappeared entirely.
//
// So the chrome is drawn into an image, uploaded, and composited here, inside
// the same pass. That is also the only form a browser can use, and it is what
// `kind == "text"` labels will need -- so the awkward-looking answer is the one
// that generalises.
//
// The image arrives **premultiplied**, because that is what Qt paints into and
// because compositing a stack of glyphs is only associative that way.

struct OverlayOut {
    @builtin(position) clip : vec4<f32>,
    @location(0) uv         : vec2<f32>,
};

@group(1) @binding(0) var overlayTex : texture_2d<f32>;
@group(1) @binding(1) var overlaySampler : sampler;

@vertex
fn vs_overlay(@builtin(vertex_index) vertexIndex : u32) -> OverlayOut {
    // A full-target triangle strip as two triangles, from the index alone.
    var corners = array<vec2<f32>, 6>(
        vec2<f32>(-1.0, -1.0), vec2<f32>( 1.0, -1.0), vec2<f32>( 1.0,  1.0),
        vec2<f32>(-1.0, -1.0), vec2<f32>( 1.0,  1.0), vec2<f32>(-1.0,  1.0),
    );
    let c = corners[vertexIndex];
    var out : OverlayOut;
    out.clip = vec4<f32>(c, 0.0, 1.0);
    // Clip space is y-up and an image is y-down.
    out.uv = vec2<f32>(c.x * 0.5 + 0.5, 0.5 - c.y * 0.5);
    return out;
}

@fragment
fn fs_overlay(in: OverlayOut) -> @location(0) vec4<f32> {
    return textureSample(overlayTex, overlaySampler, in.uv);
}
