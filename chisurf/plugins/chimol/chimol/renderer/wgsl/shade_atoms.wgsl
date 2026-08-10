// Gaussian-weighted colour and density gradient at every mesh vertex.
//
// The CPU route has to enumerate every (vertex, atom) pair into arrays and then
// scatter-add over them, because that is the only shape NumPy is fast in. Here
// each vertex keeps its own running sums in registers and the pairs never
// exist -- which is why this kernel is the one worth moving, and why the
// awkwardness of the NumPy version is not a sign the algorithm is wrong.
//
// Output is eight floats per vertex: RGBA sum, gradient, weight sum. One buffer
// rather than three, so the dispatch has one binding to write and the host one
// readback to wait on.

@group(0) @binding(0) var<storage, read> verts: array<vec4<f32>>;
// xyz = atom position, w = its Gaussian sigma.
@group(0) @binding(1) var<storage, read> atoms: array<vec4<f32>>;
@group(0) @binding(2) var<storage, read> atom_colors: array<vec4<f32>>;
@group(0) @binding(3) var<storage, read> cell_start: array<u32>;
@group(0) @binding(4) var<storage, read> cell_order: array<u32>;
@group(0) @binding(5) var<uniform> info: GridInfo;
@group(0) @binding(6) var<storage, read_write> result: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let i = gid.x;
    if (i >= info.work_items) {
        return;
    }

    let vertex = verts[i].xyz;
    let home = cell_of(info, vertex);
    // Strictly inside the cutoff, matching the CPU route, which uses the
    // largest float below it rather than `<=`.
    let cutoff2 = info.radius * info.radius;

    var colour = vec4<f32>(0.0);
    var gradient = vec3<f32>(0.0);
    var weight_sum = 0.0;

    for (var dx = -1; dx <= 1; dx = dx + 1) {
        for (var dy = -1; dy <= 1; dy = dy + 1) {
            for (var dz = -1; dz <= 1; dz = dz + 1) {
                let cell = home + vec3<i32>(dx, dy, dz);
                if (!cell_in_range(info, cell)) {
                    continue;
                }
                let slot = cell_index(info, cell);
                let first = cell_start[slot];
                let last = cell_start[slot + 1u];
                for (var k = first; k < last; k = k + 1u) {
                    let a = atoms[cell_order[k]];
                    let delta = vertex - a.xyz;
                    let d2 = dot(delta, delta);
                    if (d2 >= cutoff2) {
                        continue;
                    }
                    let s2 = a.w * a.w;
                    let w = exp(-d2 / (2.0 * s2));
                    colour = colour + w * atom_colors[cell_order[k]];
                    gradient = gradient + (w / s2) * delta;
                    weight_sum = weight_sum + w;
                }
            }
        }
    }

    let base = i * 8u;
    result[base + 0u] = colour.x;
    result[base + 1u] = colour.y;
    result[base + 2u] = colour.z;
    result[base + 3u] = colour.w;
    result[base + 4u] = gradient.x;
    result[base + 5u] = gradient.y;
    result[base + 6u] = gradient.z;
    result[base + 7u] = weight_sum;
}
