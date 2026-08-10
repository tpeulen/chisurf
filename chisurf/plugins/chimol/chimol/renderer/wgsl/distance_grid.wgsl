// Signed distance from every voxel centre to the nearest sphere *surface*.
//
// `min(|p - c_i| - r_i)`, which is an additively weighted nearest-neighbour
// query: the nearest centre is not necessarily the answer when the radii
// differ. The CPU route settles that with a k-nearest query plus a bound check;
// here the same bound falls out of the grid.
//
// Cells are searched in Chebyshev rings around the voxel's own cell. After ring
// `r` every unsearched sphere is at least `r * cell` away, so it cannot score
// below `r * cell - r_max` -- and the loop stops as soon as the best candidate
// beats that.
//
// The horizon is what keeps that from running away. A voxel in the empty corner
// of a bounding box around a globular molecule is 60 A from the nearest atom, so
// the bound above needs fifteen rings to catch up and the scan costs tens of
// thousands of cells; measured, that made this kernel *2.4x slower than the CPU
// route it replaces*. The grid is only ever read near the isosurface, at a level
// of one probe radius, so `best` starts at the horizon and any voxel further out
// than that simply reports it -- which the host does too, so the two routes agree
// by construction rather than by luck. Cells whose corners are all beyond the
// horizon cannot straddle the level, so the mesh is unchanged.

struct VoxelInfo {
    // Lower corner of voxel (0,0,0), and the voxel edge.
    origin: vec3<f32>,
    spacing: f32,
    // Voxel counts per axis, and the total, which is the dispatch size.
    dims: vec3<u32>,
    count: u32,
    // The largest sphere radius, and the cell edge, both needed by the bound.
    radius_max: f32,
    cell: f32,
    // Ring cap, and the distance beyond which a voxel just reports "far".
    max_ring: u32,
    horizon: f32,
};

// xyz = sphere centre, w = its radius.
@group(0) @binding(0) var<storage, read> spheres: array<vec4<f32>>;
@group(0) @binding(1) var<storage, read> cell_start: array<u32>;
@group(0) @binding(2) var<storage, read> cell_order: array<u32>;
@group(0) @binding(3) var<uniform> info: GridInfo;
@group(0) @binding(4) var<uniform> voxels: VoxelInfo;
@group(0) @binding(5) var<storage, read_write> result: array<f32>;

fn scan_cell(position: vec3<f32>, cell: vec3<i32>, best: f32) -> f32 {
    if (!cell_in_range(info, cell)) {
        return best;
    }
    var found = best;
    let slot = cell_index(info, cell);
    let first = cell_start[slot];
    let last = cell_start[slot + 1u];
    for (var k = first; k < last; k = k + 1u) {
        let sphere = spheres[cell_order[k]];
        let score = length(sphere.xyz - position) - sphere.w;
        found = min(found, score);
    }
    return found;
}

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let i = gid.x;
    if (i >= voxels.count) {
        return;
    }

    // Unpack the linear index the same way the host will read the result: x
    // slowest, z fastest, matching NumPy's C order.
    let nz = voxels.dims.z;
    let ny = voxels.dims.y;
    let iz = i % nz;
    let iy = (i / nz) % ny;
    let ix = i / (nz * ny);
    let position = voxels.origin
        + vec3<f32>(f32(ix), f32(iy), f32(iz)) * voxels.spacing;

    let home = cell_of(info, position);
    var best = voxels.horizon;
    var ring: u32 = 0u;
    loop {
        let r = i32(ring);
        // Ring `r` is the shell of cells at Chebyshev distance exactly r. Only
        // the six faces of the cube are new -- the interior was scanned by an
        // earlier ring -- so x and y sweep the full square and z takes either
        // both faces or the whole span, rather than the whole cube being walked
        // and 90 % of it skipped by a test.
        for (var dx = -r; dx <= r; dx = dx + 1) {
            for (var dy = -r; dy <= r; dy = dy + 1) {
                let on_side = (abs(dx) == r) || (abs(dy) == r);
                if (on_side) {
                    for (var dz = -r; dz <= r; dz = dz + 1) {
                        best = scan_cell(position, home + vec3<i32>(dx, dy, dz), best);
                    }
                } else {
                    best = scan_cell(position, home + vec3<i32>(dx, dy, -r), best);
                    if (r > 0) {
                        best = scan_cell(position, home + vec3<i32>(dx, dy, r), best);
                    }
                }
            }
        }
        // Everything left is at least `ring * cell` away.
        let bound = f32(ring) * voxels.cell - voxels.radius_max;
        if (best <= bound || ring >= voxels.max_ring) {
            break;
        }
        ring = ring + 1u;
    }

    result[i] = min(best, voxels.horizon);
}
