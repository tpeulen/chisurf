// Capped-cylinder impostors: one analytic cylinder per bond, as two triangles.
//
// Why not a tessellated cylinder
// ------------------------------
// `_build_stick_mesh` sweeps a twelve-sided tube along every bond: 33,216
// vertices and 11,072 triangles for T4 lysozyme's sticks, rebuilt in NumPy every
// time anything about the scene changes. An impostor is **two** triangles per
// bond, and it is not the cheaper approximation of the two -- it is the exact
// cylinder, where a twelve-sided tube is a prism whose silhouette is visibly
// faceted at close range.
//
// This is the same argument `impostor.wgsl` makes for spheres, and the two
// shaders are deliberately similar: a screen-facing quad sized to contain the
// primitive, an analytic intersection in the fragment stage, and `frag_depth`
// written from the hit so the primitive interpenetrates its neighbours instead
// of sorting against them as a flat card.
//
// The one thing a stick needs that a sphere does not is **two colours**. PyMOL
// splits a bond at its midpoint so each half carries its atom's colour, and a
// single-colour cylinder makes a heteroatom bond read as belonging to whichever
// end won. The split is a plane test on the hit point, which costs one dot
// product.

struct InstanceIn {
    // xyz start, w radius (model units)
    @location(0) startRadius : vec4<f32>,
    // xyz end, w unused
    @location(1) endPad      : vec4<f32>,
    @location(2) colourStart : vec4<f32>,
    @location(3) colourEnd   : vec4<f32>,
    @location(4) occlusion   : f32,
};

struct VertexOut {
    @builtin(position) clip : vec4<f32>,
    @location(0) colourStart : vec4<f32>,
    @location(1) colourEnd   : vec4<f32>,
    // The cylinder in *view* space: the fragment stage intersects there, so it
    // needs no matrices and no inverse.
    @location(2) baseView    : vec3<f32>,
    @location(3) axisView    : vec3<f32>,
    @location(4) cornerView  : vec3<f32>,
    @location(5) radiusOcc   : vec2<f32>,
};

//: How much wider than the radius the quad is drawn. As with the sphere: the
//: silhouette of a cylinder in perspective is slightly larger than its radius,
//: and a tight quad clips the rim of every near bond.
const QUAD_GROWTH : f32 = 1.4;

struct FragOut {
    @location(0) colour : vec4<f32>,
    @builtin(frag_depth) depth : f32,
};

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

    let a = (u.view * vec4<f32>(inst.startRadius.xyz, 1.0)).xyz;
    let b = (u.view * vec4<f32>(inst.endPad.xyz, 1.0)).xyz;
    let radius = inst.startRadius.w;

    // A quad around the whole segment, built in view space so it faces the
    // camera by construction. Its half-extents are the segment's own extent
    // plus the radius on both axes -- cheaper than projecting the exact
    // silhouette and wrong only by fragments the intersection discards.
    let mid = 0.5 * (a + b);
    let half = 0.5 * abs(b - a) + vec3<f32>(radius, radius, radius) * QUAD_GROWTH;

    var out : VertexOut;
    out.cornerView = mid + vec3<f32>(corner * half.xy, 0.0);
    out.clip        = u.proj * vec4<f32>(out.cornerView, 1.0);
    out.colourStart = inst.colourStart;
    out.colourEnd   = inst.colourEnd;
    out.baseView    = a;
    out.axisView    = b - a;
    out.radiusOcc   = vec2<f32>(radius, clamp(inst.occlusion, 0.0, 1.0));
    return out;
}

@fragment
fn fs_main(in: VertexOut) -> FragOut {
    let dir = normalize(in.cornerView);
    let radius = in.radiusOcc.x;
    let axisLength = length(in.axisView);
    if (axisLength < 1e-6) {
        discard;
    }
    let axis = in.axisView / axisLength;

    // Ray-cylinder in view space, with the eye at the origin. Solve in the
    // plane perpendicular to the axis: the components of the ray and of the
    // eye-to-base vector that survive the projection are what intersect the
    // circle.
    let oc = -in.baseView;
    let dPerp = dir - axis * dot(dir, axis);
    let ocPerp = oc - axis * dot(oc, axis);

    let qa = dot(dPerp, dPerp);
    let qb = dot(dPerp, ocPerp);
    let qc = dot(ocPerp, ocPerp) - radius * radius;

    var t = -1.0;
    var normal = vec3<f32>(0.0, 0.0, 1.0);

    if (qa > 1e-12) {
        let disc = qb * qb - qa * qc;
        if (disc >= 0.0) {
            let root = sqrt(disc);
            // Near root first; the far one is the inside of the tube, which is
            // what a camera inside a bond sees.
            // Roots of `qa t^2 + 2 qb t + qc = 0` with `qb = dot(dPerp, ocPerp)`
            // and `ocPerp` measured *from the base to the eye*, so the near
            // root is `(-qb - root) / qa`. Getting this sign wrong does not
            // produce nothing -- it produces a few correct pixels per bond,
            // which reads as a scatter of specks rather than as an error.
            var candidate = (-qb - root) / qa;
            var along = dot(dir * candidate - in.baseView, axis);
            if (candidate <= 0.0 || along < 0.0 || along > axisLength) {
                candidate = (-qb + root) / qa;
                along = dot(dir * candidate - in.baseView, axis);
            }
            if (candidate > 0.0 && along >= 0.0 && along <= axisLength) {
                t = candidate;
                let hit = dir * t;
                normal = normalize(hit - (in.baseView + axis * along));
            }
        }
    }

    // The caps. A stick without them is a tube you can see down when a bond
    // points at the camera, and at a chain's end there is no atom to plug it.
    let denom = dot(dir, axis);
    if (abs(denom) > 1e-6) {
        for (var end = 0; end < 2; end = end + 1) {
            let centre = in.baseView + axis * (f32(end) * axisLength);
            let capT = dot(centre, axis) / denom;
            if (capT <= 0.0) {
                continue;
            }
            if (t > 0.0 && capT >= t) {
                continue;
            }
            let hit = dir * capT;
            let offset = hit - centre;
            if (dot(offset, offset) <= radius * radius) {
                t = capT;
                normal = select(axis, -axis, end == 0);
            }
        }
    }

    if (t <= 0.0) {
        discard;
    }

    let hit = dir * t;
    // The colour split, at the midpoint plane: each half carries its own atom's
    // colour, as PyMOL's sticks do.
    let fraction = clamp(dot(hit - in.baseView, axis) / axisLength, 0.0, 1.0);
    let colour = select(in.colourEnd, in.colourStart, fraction < 0.5);

    var s : Surface;
    s.colour    = colour;
    s.normal    = normal;
    s.viewPos   = hit;
    s.occlusion = in.radiusOcc.y;

    let clip = u.proj * vec4<f32>(hit, 1.0);

    var out : FragOut;
    out.colour = shade(s, true);
    out.depth  = clip.z / clip.w;
    return out;
}
