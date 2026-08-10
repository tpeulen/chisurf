// Where each welded marching-cubes vertex sits, and which way it faces.
//
// The host decides *which* grid edges carry a vertex -- that is the triangle
// table and a `unique`, both small -- and this places them. Doing it here is
// what lets the volume stay on the GPU: the alternative is reading 8 MB back so
// that a few tens of thousands of scattered lookups can be done in NumPy.
//
// The normal is the grid's gradient, trilinearly sampled, exactly as
// `numpy.gradient` plus `_sample_gradient` computed it: central differences in
// the interior and one-sided at the faces, evaluated at the eight nodes around
// the vertex and interpolated between them. Matching that rule rather than
// inventing a cleaner one is the point -- the CPU route is the reference, and a
// surface lit differently by the two would be a difference nobody could explain.

struct VertexInfo {
    dims: vec3<u32>,
    level: f32,
    count: u32,
    _pad0: u32,
    _pad1: u32,
    _pad2: u32,
};

@group(0) @binding(0) var<storage, read> grid: array<f32>;
// One grid-edge id per vertex: axis * (nx*ny*nz) + flat index of its lower node.
@group(0) @binding(1) var<storage, read> edges: array<u32>;
@group(0) @binding(2) var<uniform> info: VertexInfo;
// Eight floats per vertex: position, then gradient, then two unused.
@group(0) @binding(3) var<storage, read_write> result: array<f32>;

fn at(i: i32, j: i32, k: i32) -> f32 {
    let ny = i32(info.dims.y);
    let nz = i32(info.dims.z);
    return grid[u32((i * ny + j) * nz + k)];
}

// `numpy.gradient`'s rule along one axis at one node.
fn slope(node: vec3<i32>, axis: i32) -> f32 {
    let n = i32(info.dims[axis]);
    var lo = node;
    var hi = node;
    var span = 2.0;
    if (node[axis] <= 0) {
        hi[axis] = 1;
        lo[axis] = 0;
        span = 1.0;
    } else if (node[axis] >= n - 1) {
        hi[axis] = n - 1;
        lo[axis] = n - 2;
        span = 1.0;
    } else {
        hi[axis] = node[axis] + 1;
        lo[axis] = node[axis] - 1;
    }
    return (at(hi.x, hi.y, hi.z) - at(lo.x, lo.y, lo.z)) / span;
}

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let v = gid.x;
    if (v >= info.count) {
        return;
    }

    let nx = info.dims.x;
    let ny = info.dims.y;
    let nz = info.dims.z;
    let volume = nx * ny * nz;

    let id = edges[v];
    let axis = id / volume;
    var rest = id % volume;
    let i = rest / (ny * nz);
    rest = rest % (ny * nz);
    let j = rest / nz;
    let k = rest % nz;

    var step = vec3<i32>(0, 0, 0);
    step[axis] = 1;
    let lower = vec3<i32>(i32(i), i32(j), i32(k));
    let upper = lower + step;

    let below = at(lower.x, lower.y, lower.z);
    let above = at(upper.x, upper.y, upper.z);
    let span = above - below;
    // A flat edge has no crossing to locate; the midpoint is what the tables
    // assume, and dividing by the span would be a division by zero.
    var mu = 0.5;
    if (abs(span) >= 1.0e-12) {
        mu = (info.level - below) / span;
    }
    let position = vec3<f32>(lower) + mu * vec3<f32>(step);

    // Trilinear sample of the gradient field at `position`.
    let limit = vec3<f32>(f32(nx - 1u), f32(ny - 1u), f32(nz - 1u));
    let clamped = clamp(position, vec3<f32>(0.0), limit);
    let corner = min(vec3<i32>(floor(clamped)), vec3<i32>(limit) - vec3<i32>(1));
    let frac = clamped - vec3<f32>(corner);

    var gradient = vec3<f32>(0.0);
    for (var dx = 0; dx < 2; dx = dx + 1) {
        let wx = select(1.0 - frac.x, frac.x, dx == 1);
        for (var dy = 0; dy < 2; dy = dy + 1) {
            let wy = select(1.0 - frac.y, frac.y, dy == 1);
            for (var dz = 0; dz < 2; dz = dz + 1) {
                let wz = select(1.0 - frac.z, frac.z, dz == 1);
                let node = corner + vec3<i32>(dx, dy, dz);
                let w = wx * wy * wz;
                gradient = gradient + w * vec3<f32>(
                    slope(node, 0), slope(node, 1), slope(node, 2)
                );
            }
        }
    }

    let base = v * 8u;
    result[base] = position.x;
    result[base + 1u] = position.y;
    result[base + 2u] = position.z;
    result[base + 3u] = 0.0;
    result[base + 4u] = gradient.x;
    result[base + 5u] = gradient.y;
    result[base + 6u] = gradient.z;
    result[base + 7u] = 0.0;
}
