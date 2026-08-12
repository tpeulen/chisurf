// Density grid accumulation from a point cloud (Gaussian or Wyvill falloff).
//
// Computed per voxel on the GPU: dispatches one thread per voxel in C order
// (x slowest, z fastest), querying a host-built uniform grid of edge
// `max_sigma * cutoff_factor` so that all contributions fall within the voxel's
// 27-cell neighbourhood.

struct VoxelInfo {
    origin: vec3<f32>,
    spacing: f32,
    dims: vec3<u32>,
    count: u32,
    cutoff_factor: f32,
    field_type: u32,  // 0 = gaussian, 1 = wyvill
    _pad0: f32,
    _pad1: f32,
};

@group(0) @binding(0) var<storage, read> spheres: array<vec4<f32>>;
@group(0) @binding(1) var<storage, read> cell_start: array<u32>;
@group(0) @binding(2) var<storage, read> cell_order: array<u32>;
@group(0) @binding(3) var<uniform> info: GridInfo;
@group(0) @binding(4) var<uniform> voxels: VoxelInfo;
@group(0) @binding(5) var<storage, read_write> result: array<f32>;

fn scan_cell_density(position: vec3<f32>, cell: vec3<i32>) -> f32 {
    if (!cell_in_range(info, cell)) {
        return 0.0;
    }
    var sum: f32 = 0.0;
    let slot = cell_index(info, cell);
    let first = cell_start[slot];
    let last = cell_start[slot + 1u];
    for (var k = first; k < last; k = k + 1u) {
        let sphere = spheres[cell_order[k]];
        let d2 = dot(sphere.xyz - position, sphere.xyz - position);
        let sigma = sphere.w;
        if (voxels.field_type == 0u) {
            sum += exp(-d2 / (2.0 * sigma * sigma));
        } else {
            let r2 = sigma * sigma;
            if (d2 < r2) {
                let u = d2 / r2;
                let u2 = u * u;
                sum += (9.0 - 22.0 * u + 17.0 * u2 - 4.0 * u2 * u) / 9.0;
            }
        }
    }
    return sum;
}

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let i = gid.x;
    if (i >= voxels.count) {
        return;
    }

    let nz = voxels.dims.z;
    let ny = voxels.dims.y;
    let iz = i % nz;
    let iy = (i / nz) % ny;
    let ix = i / (nz * ny);
    let position = voxels.origin
        + vec3<f32>(f32(ix), f32(iy), f32(iz)) * voxels.spacing;

    let home = cell_of(info, position);
    var total_density: f32 = 0.0;
    for (var dx = -1; dx <= 1; dx = dx + 1) {
        for (var dy = -1; dy <= 1; dy = dy + 1) {
            for (var dz = -1; dz <= 1; dz = dz + 1) {
                total_density += scan_cell_density(position, home + vec3<i32>(dx, dy, dz));
            }
        }
    }

    result[i] = total_density;
}
