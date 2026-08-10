// Uniform-grid neighbour lookup, shared by every compute kernel here.
//
// WGSL has no #include, so this file is prepended to each entry-point shader by
// `compute.load_compute_wgsl` -- the same composition-by-concatenation rule the
// render shaders use, and the one a browser build has to follow anyway.
//
// The grid is built host-side (see `compute.build_grid`): one cell per query
// radius, points sorted by cell, and a prefix sum into that sorted order. A cell
// equal to the radius is what makes 27 cells sufficient -- every point within
// the radius of a query lies in the query's own cell or one of its 26
// neighbours, with no ring expansion and no data-dependent loop bound.

struct GridInfo {
    // Lower corner of cell (0,0,0), and the reciprocal of the cell edge.
    origin: vec3<f32>,
    inv_cell: f32,
    // Cell counts per axis, and how many work items the dispatch really has --
    // the launch is rounded up to whole workgroups, so every kernel must guard.
    dims: vec3<u32>,
    work_items: u32,
    // Two kernel-specific scalars; what they mean is the kernel's business.
    radius: f32,
    strength: f32,
    _pad0: f32,
    _pad1: f32,
};

// Which cell a world position falls in, clamped to the grid. Clamping rather
// than rejecting matters: a query point may sit outside the bounds of the
// *occluder* set entirely, and it should still find the occluders on the near
// face rather than nothing at all.
fn cell_of(info: GridInfo, position: vec3<f32>) -> vec3<i32> {
    let raw = floor((position - info.origin) * info.inv_cell);
    let upper = vec3<f32>(info.dims) - vec3<f32>(1.0);
    return vec3<i32>(clamp(raw, vec3<f32>(0.0), upper));
}

fn cell_index(info: GridInfo, cell: vec3<i32>) -> u32 {
    let d = vec3<i32>(info.dims);
    return u32((cell.x * d.y + cell.y) * d.z + cell.z);
}

fn cell_in_range(info: GridInfo, cell: vec3<i32>) -> bool {
    let d = vec3<i32>(info.dims);
    return all(cell >= vec3<i32>(0)) && all(cell < d);
}
