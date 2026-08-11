// Selection markers: PyMOL's indicator, as three concentric screen-space squares.
//
// Why this is not the impostor shader with a flag
// -----------------------------------------------
// It shares the impostor's *instance* layout -- centre, size, colour -- and
// nothing else. An impostor intersects a ray with a sphere, shades the hit and
// writes its depth; a marker is a flat unlit stamp that must look identical
// whatever the light is doing, because its job is to be *seen*. Branching one
// shader between the two would put a lighting calculation and a ray-sphere
// intersection in the path of a glyph that needs neither.
//
// It also fixes the symptom that made this necessary. Selection markers were
// drawn by the impostor pipeline, which reads only the size -- so a selection
// came out as a scatter of small pink *spheres*, shaded and depth-cued like
// atoms, over the molecule. That reads as noise rather than as a selection,
// which is exactly how it was reported.
//
// PyMOL's `ExecutiveSetupIndicatorPassMultipassImmediate` draws three filled
// squares at each selected atom: the selection colour at full width, black at
// about half, and white in the middle. Loud on purpose -- a selection you have
// to hunt for is one you act on by mistake.

struct InstanceIn {
    // xyz centre in world space, w half-size (pixels, unless flags.w says the
    // host meant world units -- the same convention as `impostor.wgsl`)
    @location(0) sphere    : vec4<f32>,
    @location(1) colour    : vec4<f32>,
    @location(2) occlusion : f32,
};

struct VertexOut {
    @builtin(position) clip : vec4<f32>,
    @location(0) colour     : vec4<f32>,
    // Position within the marker, in [-1, 1] on both axes. The fragment stage
    // needs nothing else: the bands are a function of this alone, so the marker
    // is the same size in pixels wherever it lands.
    @location(1) local      : vec2<f32>,
};

//: Where the bands sit, as a fraction of the half-size. Outside `MID` is the
//: selection colour, between `MID` and `CORE` is black, inside `CORE` is white.
//: PyMOL's are 1.0 / 0.6 / 0.25 of the width; the black ring is what keeps the
//: marker readable against both a pale cartoon and a dark background.
const MID  : f32 = 0.6;
const CORE : f32 = 0.25;

const BLACK : vec4<f32> = vec4<f32>(0.0, 0.0, 0.0, 1.0);
const WHITE : vec4<f32> = vec4<f32>(1.0, 1.0, 1.0, 1.0);

@vertex
fn vs_main(
    @builtin(vertex_index) vertexIndex : u32,
    inst: InstanceIn,
) -> VertexOut {
    var corners = array<vec2<f32>, 6>(
        vec2<f32>(-1.0, -1.0), vec2<f32>( 1.0, -1.0), vec2<f32>( 1.0,  1.0),
        vec2<f32>(-1.0, -1.0), vec2<f32>( 1.0,  1.0), vec2<f32>(-1.0,  1.0),
    );
    let corner = corners[vertexIndex];

    let centreView = (u.view * vec4<f32>(inst.sphere.xyz, 1.0)).xyz;

    // A pixel size converted to a view-space extent at this marker's depth --
    // `pointScale` is pixels per world unit at unit depth, so the inverse is a
    // division by it. This is what makes the marker the *same size on screen*
    // however far away the atom is, which is the whole point of an indicator.
    var halfSize = inst.sphere.w;
    if (u.flags.w <= 0.5) {
        halfSize = inst.sphere.w * max(-centreView.z, 1e-3) / max(u.flags.z, 1e-6);
    }

    var out : VertexOut;
    out.clip   = u.proj * vec4<f32>(centreView + vec3<f32>(corner * halfSize, 0.0), 1.0);
    out.colour = inst.colour;
    out.local  = corner;
    return out;
}

@fragment
fn fs_main(in: VertexOut) -> @location(0) vec4<f32> {
    // A square, not a disc: no discard, and the extent is `max(|x|, |y|)`.
    let extent = max(abs(in.local.x), abs(in.local.y));
    if (extent < CORE) {
        return WHITE;
    }
    if (extent < MID) {
        return BLACK;
    }
    return in.colour;
}
