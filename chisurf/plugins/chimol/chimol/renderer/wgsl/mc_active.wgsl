// Which cells of a scalar grid the isosurface actually crosses.
//
// This is the part of marching cubes that touches every cell -- eight corner
// comparisons bit-packed into a case index -- and on a 128^3 grid that is two
// million cells of which perhaps a hundred thousand matter. Everything after it
// (the triangle table, the vertex welding, the interpolation) is a hundred times
// smaller and stays on the host, where it is already one array operation each.
//
// Compaction is one `atomicAdd` per surviving cell, which is a few tens of
// thousands of atomics rather than millions -- cheap, and no prefix-sum pass. It
// makes the output order arbitrary, so the host sorts it; the mesh would be the
// same either way, but a vertex order that changes between runs would make every
// comparison against a stored mesh useless.

struct CellInfo {
    dims: vec3<u32>,
    level: f32,
    // Cells, not voxels: one fewer along each axis.
    cells: vec3<u32>,
    capacity: u32,
};

@group(0) @binding(0) var<storage, read> grid: array<f32>;
@group(0) @binding(1) var<uniform> info: CellInfo;
// Element 0 is the count; the rest are cell indices.
@group(0) @binding(2) var<storage, read_write> crossings: array<atomic<u32>>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let cell = gid.x;
    let total = info.cells.x * info.cells.y * info.cells.z;
    if (cell >= total) {
        return;
    }
    let cz = cell % info.cells.z;
    let cy = (cell / info.cells.z) % info.cells.y;
    let cx = cell / (info.cells.z * info.cells.y);

    let ny = info.dims.y;
    let nz = info.dims.z;
    let base = (cx * ny + cy) * nz + cz;
    let dx = ny * nz;
    let dy = nz;

    // Lorensen-Cline corner order: 0:(0,0,0) 1:(1,0,0) 2:(1,1,0) 3:(0,1,0)
    //                              4:(0,0,1) 5:(1,0,1) 6:(1,1,1) 7:(0,1,1)
    var mask: u32 = 0u;
    if (grid[base] < info.level) { mask = mask | 1u; }
    if (grid[base + dx] < info.level) { mask = mask | 2u; }
    if (grid[base + dx + dy] < info.level) { mask = mask | 4u; }
    if (grid[base + dy] < info.level) { mask = mask | 8u; }
    if (grid[base + 1u] < info.level) { mask = mask | 16u; }
    if (grid[base + dx + 1u] < info.level) { mask = mask | 32u; }
    if (grid[base + dx + dy + 1u] < info.level) { mask = mask | 64u; }
    if (grid[base + dy + 1u] < info.level) { mask = mask | 128u; }

    if (mask == 0u || mask == 255u) {
        return;
    }
    let slot = atomicAdd(&crossings[0], 1u);
    if (slot < info.capacity) {
        atomicStore(&crossings[slot + 1u], cell);
    }
}
