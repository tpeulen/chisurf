// Exact squared Euclidean distance transform, one axis per dispatch.
//
// Felzenszwalb-Huttenlocher: the squared EDT of a d-dimensional field is d
// one-dimensional transforms, one along each axis, and each of those is a lower
// envelope of parabolas found in a single forward scan. The scan is sequential
// -- it maintains a stack of the parabolas still on the envelope -- but the
// *lines* are completely independent, which is what makes this a compute kernel:
// 16k lines of 128 voxels at 128^3, one invocation each.
//
// Two things the shape of this forces.
//
// The per-line stacks live in storage rather than in registers, because WGSL
// wants a compile-time size for a function-scope array and the line length is
// the grid's. Each invocation owns its own slice, so there is nothing to
// synchronise.
//
// The pass is **not** in place. At position `q` the parabola that wins can be
// centred to the *right* of `q`, so writing the answer into `src[q]` would
// corrupt an input a later `q` still needs. Source and destination are separate
// buffers and the host swaps them between axes.

struct EdtInfo {
    dims: vec3<u32>,
    axis: u32,
    // Voxels per line along `axis`, and how many lines this dispatch has.
    length: u32,
    lines: u32,
    _pad0: u32,
    _pad1: u32,
};

@group(0) @binding(0) var<storage, read> src: array<f32>;
@group(0) @binding(1) var<storage, read_write> hull: array<i32>;
@group(0) @binding(2) var<storage, read_write> boundary: array<f32>;
@group(0) @binding(3) var<uniform> edt: EdtInfo;
@group(0) @binding(4) var<storage, read_write> dst: array<f32>;

//: Stands in for infinity. Large enough that no real squared distance in a
//: molecular grid can reach it, small enough that adding `q*q` cannot overflow.
const BIG: f32 = 1.0e20;

// Flat index of position `q` along `axis` on line `line`, in C order.
fn voxel_of(line: u32, q: u32) -> u32 {
    let ny = edt.dims.y;
    let nz = edt.dims.z;
    if (edt.axis == 0u) {
        return (q * ny + line / nz) * nz + line % nz;
    }
    if (edt.axis == 1u) {
        return ((line / nz) * ny + q) * nz + line % nz;
    }
    return ((line / ny) * ny + line % ny) * nz + q;
}

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let line = gid.x;
    if (line >= edt.lines) {
        return;
    }
    let n = edt.length;
    if (n == 0u) {
        return;
    }
    let base = line * (n + 1u);

    // Forward scan: build the lower envelope.
    var k: i32 = 0;
    hull[base] = 0;
    boundary[base] = -BIG;
    boundary[base + 1u] = BIG;
    for (var q: u32 = 1u; q < n; q = q + 1u) {
        let fq = src[voxel_of(line, q)];
        let x = f32(q);
        var s = 0.0;
        loop {
            let p = u32(hull[base + u32(k)]);
            let fp = src[voxel_of(line, p)];
            let xp = f32(p);
            s = ((fq + x * x) - (fp + xp * xp)) / (2.0 * x - 2.0 * xp);
            if (s > boundary[base + u32(k)] || k == 0) {
                break;
            }
            k = k - 1;
        }
        k = k + 1;
        hull[base + u32(k)] = i32(q);
        boundary[base + u32(k)] = s;
        boundary[base + u32(k) + 1u] = BIG;
    }

    // Second scan: read the envelope off in order.
    var read: i32 = 0;
    for (var q: u32 = 0u; q < n; q = q + 1u) {
        let x = f32(q);
        while (boundary[base + u32(read) + 1u] < x) {
            read = read + 1;
        }
        let p = u32(hull[base + u32(read)]);
        let dq = x - f32(p);
        dst[voxel_of(line, q)] = dq * dq + src[voxel_of(line, p)];
    }
}
