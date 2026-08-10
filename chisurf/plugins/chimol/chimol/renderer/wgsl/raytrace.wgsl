// The ray tracer, as a compute shader.
//
// One invocation per *output* pixel, looping over its supersamples inside, so
// there is no atomic accumulation and no second resolve pass. Each ray walks
// *through* the scene rather than stopping at the first surface: every hit
// contributes its alpha and the remainder is passed along, so a translucent
// surface shows what is behind it.
//
// The shading is PyMOL's, transcribed from `layer1/Ray.cpp` and unchanged from
// the CPU tracer this replaces -- including the part that was missing for a
// long time. PyMOL's brightness has **two** diffuse terms:
//
//   bright = ambient
//          + ((1-direct_shade) + direct_shade*lit) * direct * direct_cmp
//          + lreflect * reflect_cmp
//
// `direct_cmp` is `pow(surfnormal[2], power)` -- the normal's z in camera space,
// so `direct` is a **headlight**: a surface facing the viewer is lit whatever
// the lamps are doing. Without it the ceiling is ambient + diffuse = 0.59 and
// only where a lamp faces the surface squarely, against PyMOL's 0.14 + 0.45 +
// 0.45 clamped to 1, which is why a traced image used to come out far darker
// than the viewport it was meant to reproduce.

struct TraceInfo {
    origin: vec3<f32>,
    fov: f32,
    forward: vec3<f32>,
    ssaa: u32,
    up: vec3<f32>,
    max_layers: u32,
    background: vec3<f32>,
    ambient: f32,

    width: u32,
    height: u32,
    diffuse: f32,
    specular: f32,

    shininess: f32,
    direct_specular: f32,
    direct_specular_power: f32,
    reflect_power: f32,

    direct: f32,
    direct_power: f32,
    legacy: f32,
    shadow_fudge: f32,

    shadow_enabled: u32,
    depth_cue_enabled: u32,
    shadow_decay_factor: f32,
    shadow_decay_range: f32,

    fog_start: f32,
    fog_intensity: f32,
    fog_front: f32,
    fog_inv_range: f32,
};

// xyz = colour, w = alpha.
@group(0) @binding(7) var<storage, read> sphere_color: array<vec4<f32>>;
// Three consecutive entries per triangle, matching `tri_verts`.
@group(0) @binding(8) var<storage, read> tri_normal: array<vec4<f32>>;
// xyz = colour, w = alpha; one per triangle.
@group(0) @binding(9) var<storage, read> tri_color: array<vec4<f32>>;
// xyz = unit direction toward the light.
@group(0) @binding(10) var<storage, read> lights: array<vec4<f32>>;
@group(0) @binding(11) var<uniform> trace: TraceInfo;
// Four floats per pixel: RGB, then 1 if anything was hit at all.
@group(0) @binding(12) var<storage, read_write> pixels: array<f32>;

// How much of one light reaches a point: 1 fully lit, 0 fully shadowed.
//
// The occluder taken is the **nearest** one. PyMOL does the same, and only when
// the decay is on -- `nearest_shadow = (shadow_decay != _0)` in `layer1/Ray.cpp`
// -- because the decay is a function of how far the occluder is, so any other
// occluder answers a different question.
fn shadow_factor(point: vec3<f32>, light: vec3<f32>, skip: i32) -> f32 {
    let hit = closest_hit(point, light, 1.0e-6, 3.0e38, skip);
    if (hit.prim < 0) {
        return 1.0;
    }
    if (trace.shadow_decay_factor > 0.0) {
        let d = hit.t - trace.shadow_decay_range;
        if (d <= 0.0) {
            return 1.0;
        }
        let occlusion = 1.0 - exp(-d * trace.shadow_decay_factor);
        return max(1.0 - occlusion, 0.0);
    }
    return 0.0;
}

struct Surface {
    normal: vec3<f32>,
    color: vec3<f32>,
    alpha: f32,
};

fn surface_at(prim: i32, point: vec3<f32>) -> Surface {
    var out: Surface;
    let p = u32(prim);
    if (p < scene.n_spheres) {
        out.normal = normalize(point - spheres[p].xyz);
        out.color = sphere_color[p].xyz;
        out.alpha = sphere_color[p].w;
        return out;
    }
    let tri = p - scene.n_spheres;
    let base = tri * 3u;
    let v0 = tri_verts[base].xyz;
    let v1 = tri_verts[base + 1u].xyz;
    let v2 = tri_verts[base + 2u].xyz;
    // Barycentric coordinates of the hit, so the vertex normals interpolate.
    let e1 = v1 - v0;
    let e2 = v2 - v0;
    let rel = point - v0;
    let d00 = dot(e1, e1);
    let d01 = dot(e1, e2);
    let d11 = dot(e2, e2);
    let d20 = dot(rel, e1);
    let d21 = dot(rel, e2);
    let denom = d00 * d11 - d01 * d01;
    var u = 0.0;
    var v = 0.0;
    if (abs(denom) > 1.0e-12) {
        u = (d11 * d20 - d01 * d21) / denom;
        v = (d00 * d21 - d01 * d20) / denom;
    }
    let w = 1.0 - u - v;
    let n = w * tri_normal[base].xyz
          + u * tri_normal[base + 1u].xyz
          + v * tri_normal[base + 2u].xyz;
    let length_n = length(n);
    out.normal = select(n / length_n, vec3<f32>(0.0, 0.0, 1.0), length_n < 1.0e-9);
    out.color = tri_color[tri].xyz;
    out.alpha = tri_color[tri].w;
    return out;
}

fn shade(prim: i32, point: vec3<f32>, distance: f32, surface: Surface,
         spec_per_light: f32) -> vec3<f32> {
    let view = normalize(trace.origin - point);
    let normal = surface.normal;

    var reflect_sum = 0.0;
    var spec_sum = 0.0;
    for (var li = 0u; li < scene.n_lights; li = li + 1u) {
        let light = lights[li].xyz;
        var lit = 1.0;
        if (trace.shadow_enabled != 0u) {
            lit = shadow_factor(point + light * trace.shadow_fudge, light, prim);
        }
        let n_dot_l = clamp(dot(normal, light), 0.0, 1.0);
        if (lit > 0.0 && n_dot_l > 0.0) {
            reflect_sum = reflect_sum + lit * pow(n_dot_l, trace.reflect_power);
            let half_vector = light + view;
            let half_length = length(half_vector);
            if (half_length > 1.0e-9) {
                let n_dot_h = clamp(dot(normal, half_vector / half_length), 0.0, 1.0);
                spec_sum = spec_sum + lit * pow(n_dot_h, trace.shininess);
            }
        }
    }
    let reflect_norm = reflect_sum / f32(max(scene.n_lights, 1u));

    let n_dot_v = clamp(dot(normal, view), 0.0, 1.0);
    let direct_cmp = pow(n_dot_v, trace.direct_specular_power);

    var bright = trace.ambient
        + trace.direct * pow(n_dot_v, trace.direct_power)
        + trace.diffuse * reflect_norm;
    if (trace.legacy > 0.0) {
        let n_dot_l0 = max(dot(normal, lights[0].xyz), 0.0);
        let legacy_bright = trace.ambient + trace.diffuse * n_dot_l0;
        bright = bright * (1.0 - trace.legacy) + legacy_bright * trace.legacy;
    }
    bright = clamp(bright, 0.0, 1.0);

    let excess = clamp(
        trace.direct_specular * direct_cmp
        + trace.specular * spec_sum * spec_per_light,
        0.0, 1.0,
    );

    var colour = surface.color * bright + vec3<f32>(excess);
    if (trace.depth_cue_enabled != 0u && trace.fog_inv_range > 0.0) {
        let nd = (distance - trace.fog_front) * trace.fog_inv_range;
        if (nd > trace.fog_start) {
            let fade = min((nd - trace.fog_start) / (1.0 - trace.fog_start)
                           * trace.fog_intensity, 1.0);
            if (fade > 0.0) {
                colour = mix(colour, trace.background, fade);
            }
        }
    }
    return colour;
}

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let pixel = gid.x;
    if (pixel >= scene.work_items) {
        return;
    }
    let px = pixel % trace.width;
    let py = pixel / trace.width;

    // The camera basis is re-orthogonalised here, not on the host, so a `up`
    // that is not exactly perpendicular to `forward` cannot skew the frame.
    var right = cross(trace.forward, trace.up);
    let right_length = length(right);
    right = select(right / right_length, vec3<f32>(1.0, 0.0, 0.0),
                   right_length < 1.0e-9);
    let up = normalize(cross(right, trace.forward));

    let ssaa = max(trace.ssaa, 1u);
    let rw = trace.width * ssaa;
    let rh = trace.height * ssaa;
    let half_h = tan(trace.fov * 0.5);
    let half_w = half_h * f32(rw) / f32(max(rh, 1u));
    let spec_per_light = 1.0 / pow(f32(max(scene.n_lights - 1u, 1u)), 0.6);

    var total = vec3<f32>(0.0);
    var samples = 0.0;
    var any_hit = false;

    for (var sy = 0u; sy < ssaa; sy = sy + 1u) {
        for (var sx = 0u; sx < ssaa; sx = sx + 1u) {
            let sub_x = px * ssaa + sx;
            let sub_y = py * ssaa + sy;
            let u = (f32(sub_x) + 0.5) / f32(max(rw - 1u, 1u)) - 0.5;
            let v = 0.5 - (f32(sub_y) + 0.5) / f32(max(rh - 1u, 1u));
            var dir = trace.forward
                + right * (u * 2.0 * half_w)
                + up * (v * 2.0 * half_h);
            let dir_length = length(dir);
            dir = select(dir / dir_length, trace.forward, dir_length < 1.0e-9);

            var accumulated = vec3<f32>(0.0);
            var transmitted = 1.0;
            var t_min = 1.0e-6;
            var hit_here = false;
            for (var layer = 0u; layer < trace.max_layers; layer = layer + 1u) {
                let hit = closest_hit(trace.origin, dir, t_min, 3.0e38, -1);
                if (hit.prim < 0) {
                    break;
                }
                let point = trace.origin + dir * hit.t;
                let surface = surface_at(hit.prim, point);
                let colour = shade(hit.prim, point, hit.t, surface, spec_per_light);
                let alpha = clamp(surface.alpha, 0.0, 1.0);
                accumulated = accumulated + transmitted * alpha * colour;
                hit_here = true;
                transmitted = transmitted * (1.0 - alpha);
                // Below ~1/255 the next layer cannot change a byte.
                if (transmitted < 0.004) {
                    break;
                }
                // Step past this surface, or the next search finds it again.
                t_min = hit.t + 1.0e-4;
            }
            if (hit_here) {
                total = total + accumulated + transmitted * trace.background;
                samples = samples + 1.0;
                any_hit = true;
            }
        }
    }

    let base = pixel * 4u;
    if (any_hit) {
        let colour = total / samples;
        pixels[base] = colour.x;
        pixels[base + 1u] = colour.y;
        pixels[base + 2u] = colour.z;
        pixels[base + 3u] = 1.0;
    } else {
        pixels[base] = 0.0;
        pixels[base + 1u] = 0.0;
        pixels[base + 2u] = 0.0;
        pixels[base + 3u] = 0.0;
    }
}
