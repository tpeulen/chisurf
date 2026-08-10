// Hemispherical ambient occlusion: how much of the sky above each vertex is
// blocked by the atoms around it.
//
// Each occluder contributes the fraction of the hemisphere it covers,
// `1 - cos(alpha)` with `sin(alpha) = r / d`, weighted by the cosine between the
// vertex normal and the direction to it. The contributions combine as
// `1 - exp(-strength * sum)` rather than adding, which keeps the result below 1
// and stops a dense neighbourhood from saturating to pure black.

@group(0) @binding(0) var<storage, read> points: array<vec4<f32>>;
@group(0) @binding(1) var<storage, read> normals: array<vec4<f32>>;
// xyz = occluder centre, w = its radius.
@group(0) @binding(2) var<storage, read> occluders: array<vec4<f32>>;
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

    let position = points[i].xyz;
    let normal = normals[i].xyz;
    let home = cell_of(info, position);
    let max2 = info.radius * info.radius;

    var total = 0.0;
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
                    let d2 = dot(delta, delta);
                    // A vertex sitting inside an occluder is its own surface,
                    // not something blocking it; the lower bound keeps a
                    // coincident pair out of the division below.
                    if (d2 >= max2 || d2 <= 1.0e-12) {
                        continue;
                    }
                    let d = sqrt(d2);
                    if (d <= sphere.w) {
                        continue;
                    }
                    let cos_theta = dot(delta, normal) / d;
                    if (cos_theta <= 0.0) {
                        continue;
                    }
                    let sin_a = sphere.w / d;
                    let coverage = 1.0 - sqrt(max(1.0 - sin_a * sin_a, 0.0));
                    total = total + cos_theta * coverage;
                }
            }
        }
    }

    result[i] = 1.0 - exp(-info.strength * total);
}
