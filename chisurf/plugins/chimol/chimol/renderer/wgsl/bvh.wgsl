// BVH traversal and the two primitive intersections, shared by every shader
// that casts a ray.
//
// Prepended by concatenation (`compute.load_ray_wgsl`), because WGSL has no
// #include -- the same rule the render shaders follow, and the browser's rule
// too. `raytrace.wgsl` and `bvh_probe.wgsl` both build on this, which is what
// makes the probe worth having: the traversal a test exercises is literally the
// traversal the tracer runs, not a copy of it.
//
// Primitives live in one index space so a scene of mixed kinds is one tree:
// `prim < n_spheres` is a sphere, and anything above it is triangle
// `prim - n_spheres`. A wireframe -- round caps as spheres, shafts as triangles
// -- is the case that made a unified tree worth having over one tree per kind.

struct SceneInfo {
    // Where the index space changes kind, and how many rays the dispatch has.
    n_spheres: u32,
    n_prims: u32,
    work_items: u32,
    n_lights: u32,
};

// xyz = sphere centre, w = radius.
@group(0) @binding(0) var<storage, read> spheres: array<vec4<f32>>;
// Three consecutive entries per triangle; w is unused padding.
@group(0) @binding(1) var<storage, read> tri_verts: array<vec4<f32>>;
// Node boxes, and (left, start, count) packed as three i32 in a vec4's lanes.
@group(0) @binding(2) var<storage, read> node_lo: array<vec4<f32>>;
@group(0) @binding(3) var<storage, read> node_hi: array<vec4<f32>>;
@group(0) @binding(4) var<storage, read> node_meta: array<vec4<i32>>;
@group(0) @binding(5) var<storage, read> prim_index: array<u32>;
@group(0) @binding(6) var<uniform> scene: SceneInfo;

//: Matches `bvh.STACK_SIZE`. A tree deeper than this cannot exist -- the build
//: caps depth -- and a stack that overflowed would drop geometry out of the
//: picture rather than fail, which is the wrong way for it to go wrong.
const STACK_SIZE: u32 = 64u;

struct Hit {
    t: f32,
    prim: i32,
};

fn moller_trumbore(origin: vec3<f32>, dir: vec3<f32>,
                   v0: vec3<f32>, v1: vec3<f32>, v2: vec3<f32>) -> f32 {
    let e1 = v1 - v0;
    let e2 = v2 - v0;
    let pvec = cross(dir, e2);
    let det = dot(e1, pvec);
    if (abs(det) < 1.0e-12) {
        return -1.0;
    }
    let inv_det = 1.0 / det;
    let tvec = origin - v0;
    let u = dot(tvec, pvec) * inv_det;
    if (u < 0.0 || u > 1.0) {
        return -1.0;
    }
    let qvec = cross(tvec, e1);
    let v = dot(dir, qvec) * inv_det;
    if (v < 0.0 || u + v > 1.0) {
        return -1.0;
    }
    let t = dot(e2, qvec) * inv_det;
    if (t < 1.0e-6) {
        return -1.0;
    }
    return t;
}

// Nearest primitive the ray meets beyond `t_min`. Both kinds are intersected
// exactly -- a sphere analytically, a triangle by Moller-Trumbore -- so the tree
// changes only *which* primitives are tested, never the geometry of a hit.
//
// `skip` excludes one primitive, which is how a shadow ray ignores the surface
// it leaves from. It is a unified index, so it is right for a triangle as well
// as a sphere.
fn closest_hit(origin: vec3<f32>, dir: vec3<f32>, t_min: f32, t_limit: f32,
               skip: i32) -> Hit {
    var best: Hit;
    best.t = t_limit;
    best.prim = -1;
    if (scene.n_prims == 0u) {
        return best;
    }

    // A zero component gives an infinite slope, which the slab test handles: the
    // ray is parallel to that pair of planes and either always or never inside
    // them. The bounds are padded at build time so `0 * inf` -- the one case
    // that would give a NaN -- cannot arise.
    let inv = vec3<f32>(
        select(1.0 / dir.x, 1.0e30, dir.x == 0.0),
        select(1.0 / dir.y, 1.0e30, dir.y == 0.0),
        select(1.0 / dir.z, 1.0e30, dir.z == 0.0),
    );

    var stack: array<u32, 64>;
    var sp: u32 = 0u;
    stack[sp] = 0u;
    sp = sp + 1u;

    while (sp > 0u) {
        sp = sp - 1u;
        let node = stack[sp];

        let a = (node_lo[node].xyz - origin) * inv;
        let b = (node_hi[node].xyz - origin) * inv;
        let entry = min(a, b);
        let exit = max(a, b);
        let t_near = max(max(entry.x, entry.y), entry.z);
        let t_far = min(min(exit.x, exit.y), exit.z);
        if (t_far < t_near || t_far < t_min || t_near > best.t) {
            continue;
        }

        let link = node_meta[node];
        if (link.x >= 0) {
            stack[sp] = u32(link.x);
            sp = sp + 1u;
            stack[sp] = u32(link.x) + 1u;
            sp = sp + 1u;
            continue;
        }

        let first = u32(link.y);
        let last = first + u32(link.z);
        for (var i = first; i < last; i = i + 1u) {
            let p = prim_index[i];
            if (i32(p) == skip) {
                continue;
            }
            if (p < scene.n_spheres) {
                let s = spheres[p];
                if (s.w <= 0.0) {
                    continue;
                }
                let oc = origin - s.xyz;
                let half_b = dot(oc, dir);
                let c = dot(oc, oc) - s.w * s.w;
                let disc = half_b * half_b - c;
                if (disc < 0.0) {
                    continue;
                }
                let root = sqrt(disc);
                var th = -half_b - root;
                if (th <= t_min) {
                    th = -half_b + root;
                    if (th <= t_min) {
                        continue;
                    }
                }
                if (th < best.t) {
                    best.t = th;
                    best.prim = i32(p);
                }
            } else {
                let base = (p - scene.n_spheres) * 3u;
                let t = moller_trumbore(
                    origin, dir,
                    tri_verts[base].xyz,
                    tri_verts[base + 1u].xyz,
                    tri_verts[base + 2u].xyz,
                );
                if (t > t_min && t < best.t) {
                    best.t = t;
                    best.prim = i32(p);
                }
            }
        }
    }
    return best;
}
