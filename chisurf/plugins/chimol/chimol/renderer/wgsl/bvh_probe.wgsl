// One ray in, one nearest hit out. Exists so the traversal can be tested
// directly against an exhaustive search rather than only through a rendered
// image, and so that test exercises the *same* `closest_hit` the tracer runs
// rather than a copy of it.

// xyz = ray origin, w = t_min.
@group(0) @binding(7) var<storage, read> ray_origin: array<vec4<f32>>;
// xyz = unit direction, w = the primitive to skip, or -1.
@group(0) @binding(8) var<storage, read> ray_dir: array<vec4<f32>>;
// Two floats per ray: distance, and the primitive index as a float.
@group(0) @binding(9) var<storage, read_write> result: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let i = gid.x;
    if (i >= scene.work_items) {
        return;
    }
    let origin = ray_origin[i];
    let direction = ray_dir[i];
    let hit = closest_hit(origin.xyz, direction.xyz, origin.w, 3.0e38,
                          i32(direction.w));
    result[i * 2u] = hit.t;
    result[i * 2u + 1u] = f32(hit.prim);
}
