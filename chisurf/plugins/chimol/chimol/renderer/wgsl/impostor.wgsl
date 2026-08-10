// Sphere impostors: one analytic sphere per instance, drawn as two triangles.
//
// Why not a tessellated sphere
// ----------------------------
// A mesh sphere at chimol's subdivision costs ~270 triangles; 148L's space-fill
// is 374,112 of them. An impostor is **2**, and it is not the cheaper
// approximation of the two -- a tessellation is a polyhedron and this is the
// sphere. The scene builder already emits the bead path this way
// (`kind == "points"`, world radii), because at 234,184 beads a nuclear pore is
// 234k vertices as impostors and 37 million as meshes.
//
// The quad is built in *view* space, so it faces the camera by construction and
// no billboard rotation is needed. It is grown by a factor over the radius: the
// silhouette of a sphere seen in perspective is slightly larger than its
// radius, and a tight quad clips the rim of every near sphere.
//
// One deliberate upgrade over the OpenGL point-sprite path: this writes
// `frag_depth` from the ray-sphere hit, so an impostor *interpenetrates* its
// neighbours the way a mesh sphere does. GL computes the sphere normal but
// never writes `gl_FragDepth`, so its spheres are flat billboards that pop in
// front of each other -- the curved intersection seams between overlapping
// atoms here are the visible difference.

struct InstanceIn {
    // xyz centre in world space, w radius (world units, or pixels when the host
    // sets pointScale to 0 -- see `flags.z`)
    @location(0) sphere    : vec4<f32>,
    @location(1) colour    : vec4<f32>,
    @location(2) occlusion : f32,
};

struct VertexOut {
    @builtin(position) clip  : vec4<f32>,
    @location(0) colour      : vec4<f32>,
    // Centre and radius in *view* space: the fragment stage intersects there,
    // so it needs no matrices and no inverse.
    @location(1) centreView  : vec3<f32>,
    @location(2) radiusView  : f32,
    @location(3) cornerView  : vec3<f32>,
    @location(4) occlusion   : f32,
};

//: How much wider than the radius the quad is drawn. 1.0 clips the silhouette of
//: a sphere near the camera, because perspective makes its outline larger than
//: its radius; the excess is discarded by the intersection test and costs
//: nothing but a few fragments.
const QUAD_GROWTH : f32 = 1.5;

struct FragOut {
    @location(0) colour : vec4<f32>,
    @builtin(frag_depth) depth : f32,
};

@vertex
fn vs_main(
    @builtin(vertex_index) vertexIndex : u32,
    inst: InstanceIn,
) -> VertexOut {
    // Two triangles from six indices, with no vertex buffer: the corner is a
    // function of the index. A quad this small is cheaper to derive than to
    // upload and bind.
    var corners = array<vec2<f32>, 6>(
        vec2<f32>(-1.0, -1.0), vec2<f32>( 1.0, -1.0), vec2<f32>( 1.0,  1.0),
        vec2<f32>(-1.0, -1.0), vec2<f32>( 1.0,  1.0), vec2<f32>(-1.0,  1.0),
    );
    let corner = corners[vertexIndex];

    let centreView = (u.view * vec4<f32>(inst.sphere.xyz, 1.0)).xyz;

    // A bead's radius is a distance in the model, so it grows as the camera
    // approaches the way a mesh sphere does. Every other glyph means a count of
    // *pixels* by `radius`, and a pixel size has to be converted back into a
    // view-space extent at this fragment's depth -- `pointScale` is pixels per
    // world unit at unit depth, so the inverse is a division by it. Doing the
    // conversion here leaves the intersection below reading one radius, whatever
    // the host meant.
    var radiusView = inst.sphere.w;
    if (u.flags.w <= 0.5) {
        radiusView = inst.sphere.w * max(-centreView.z, 1e-3) / max(u.flags.z, 1e-6);
    }

    var out : VertexOut;
    out.cornerView = centreView
        + vec3<f32>(corner * radiusView * QUAD_GROWTH, 0.0);
    out.clip       = u.proj * vec4<f32>(out.cornerView, 1.0);
    out.colour     = inst.colour;
    out.centreView = centreView;
    out.radiusView = radiusView;
    out.occlusion  = clamp(inst.occlusion, 0.0, 1.0);
    return out;
}

@fragment
fn fs_main(in: VertexOut) -> FragOut {
    // The ray from the eye through this fragment, in view space. The eye is the
    // origin there, so the ray direction is the fragment's own position.
    let dir = normalize(in.cornerView);
    let oc  = -in.centreView;
    let b   = dot(oc, dir);
    let c   = dot(oc, oc) - in.radiusView * in.radiusView;
    let disc = b * b - c;
    if (disc < 0.0) {
        // Outside the sphere: the corner of the quad that is not the sphere.
        discard;
    }
    let t = -b - sqrt(disc);
    if (t <= 0.0) {
        // The camera is inside this sphere. Dropping the fragment is right --
        // the near cap would otherwise fill the screen.
        discard;
    }
    let hit = dir * t;

    var s : Surface;
    s.colour    = in.colour;
    s.normal    = (hit - in.centreView) / max(in.radiusView, 1e-6);
    s.viewPos   = hit;
    s.occlusion = in.occlusion;

    // Depth from the hit, not from the quad: this is what makes an impostor
    // intersect its neighbours instead of sorting against them as a flat card.
    let clip = u.proj * vec4<f32>(hit, 1.0);

    var out : FragOut;
    out.colour = shade(s, true);
    out.depth  = clip.z / clip.w;
    return out;
}
