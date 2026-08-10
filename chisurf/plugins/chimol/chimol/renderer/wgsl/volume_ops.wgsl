// Small whole-volume operations, so a grid never has to come back to the host
// just to be compared or scaled.
//
// The surface pipeline is distance grid -> threshold -> distance transform ->
// marching cubes, and every one of those ran on the GPU while the *grid* made
// the round trip between each pair: read back 8 MB, upload 8 MB, twice over.
// That transport is why the marching-cubes scan measured slower than the NumPy
// pass it replaced -- not the kernel. These two entry points are what let the
// chain stay resident.

struct VolumeInfo {
    count: u32,
    // `select`: below this the output is `low`, at or above it `high`.
    level: f32,
    low: f32,
    high: f32,
    // `scale`: out = src * factor + offset.
    factor: f32,
    offset: f32,
    _pad0: u32,
    _pad1: u32,
};

@group(0) @binding(0) var<storage, read> src: array<f32>;
@group(0) @binding(1) var<uniform> info: VolumeInfo;
@group(0) @binding(2) var<storage, read_write> dst: array<f32>;

// The seed for a distance transform: zero where the transform should measure
// *from*, and a stand-in for infinity everywhere else.
@compute @workgroup_size(64)
fn threshold(@builtin(global_invocation_id) gid: vec3<u32>) {
    let i = gid.x;
    if (i >= info.count) {
        return;
    }
    dst[i] = select(info.high, info.low, src[i] < info.level);
}

@compute @workgroup_size(64)
fn scale(@builtin(global_invocation_id) gid: vec3<u32>) {
    let i = gid.x;
    if (i >= info.count) {
        return;
    }
    dst[i] = src[i] * info.factor + info.offset;
}

// The distance transform produces *squared* distances; this is the root and the
// unit conversion in one pass, so the volume is not walked twice for it.
@compute @workgroup_size(64)
fn root_scale(@builtin(global_invocation_id) gid: vec3<u32>) {
    let i = gid.x;
    if (i >= info.count) {
        return;
    }
    dst[i] = sqrt(max(src[i], 0.0)) * info.factor + info.offset;
}
