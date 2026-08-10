// How much of the key light each vertex loses to the geometry around it.
//
// A ray is cast from the vertex toward the light and each nearby sphere is asked
// how close it comes to that ray. A sphere the ray passes straight through
// blocks fully; one it grazes blocks partly, which is what gives a soft edge
// rather than the hard stair-step of a shadow map at this scale.
//
// Each occluder must be counted **once**. The cell list this descends from
// stepped along the ray in strides of `max_distance` and searched a 3x3x3
// neighbourhood at each stride -- and consecutive neighbourhoods overlap, so an
// occluder in a shared cell was accumulated two or three times and the shadow it
// cast was that much too deep. Here the step is one occluder reach and each
// sphere is accepted only by the step its own distance along the ray falls in:
// `floor(along / step)`, which every sphere has exactly one of. Coverage still
// holds, because a sphere in step `s` is within one step along and one reach
// perpendicular of that step's sample point, and the cell is the larger of the
// two -- so it is always inside that sample's 3x3x3 neighbourhood.

struct ShadowInfo {
    // Unit vector pointing *toward* the light.
    light: vec3<f32>,
    max_distance: f32,
    // Step along the ray, which is also the grid cell.
    step: f32,
    steps: u32,
    softness: f32,
    strength: f32,
};

@group(0) @binding(0) var<storage, read> points: array<vec4<f32>>;
@group(0) @binding(1) var<storage, read> normals: array<vec4<f32>>;
// xyz = occluder centre, w = its radius.
@group(0) @binding(2) var<storage, read> occluders: array<vec4<f32>>;
@group(0) @binding(3) var<storage, read> cell_start: array<u32>;
@group(0) @binding(4) var<storage, read> cell_order: array<u32>;
@group(0) @binding(5) var<uniform> info: GridInfo;
@group(0) @binding(6) var<uniform> ray: ShadowInfo;
@group(0) @binding(7) var<storage, read_write> result: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let i = gid.x;
    if (i >= info.work_items) {
        return;
    }

    let position = points[i].xyz;
    // Facing away from the light: the diffuse term already darkens it, and PyMOL
    // does not shadow it either.
    if (dot(normals[i].xyz, ray.light) <= 0.0) {
        result[i] = 0.0;
        return;
    }

    var total = 0.0;
    for (var s: u32 = 0u; s < ray.steps; s = s + 1u) {
        let probe = position + ray.light * (f32(s) * ray.step);
        let home = cell_of(info, probe);
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
                        let sphere = occluders[cell_order[k]];
                        let delta = sphere.xyz - position;
                        let along = dot(delta, ray.light);
                        if (along <= 0.0 || along >= ray.max_distance) {
                            continue;
                        }
                        // The one step allowed to claim this sphere.
                        if (u32(floor(along / ray.step)) != s) {
                            continue;
                        }
                        let reach = sphere.w * ray.softness;
                        let perpendicular = delta - along * ray.light;
                        let perp2 = dot(perpendicular, perpendicular);
                        if (perp2 >= reach * reach) {
                            continue;
                        }
                        // A vertex inside the occluder is its own surface.
                        if (dot(delta, delta) <= sphere.w * sphere.w) {
                            continue;
                        }
                        let blocked = 1.0 - sqrt(perp2) / reach;
                        total = total + blocked * blocked;
                    }
                }
            }
        }
    }

    result[i] = 1.0 - exp(-ray.strength * total);
}
