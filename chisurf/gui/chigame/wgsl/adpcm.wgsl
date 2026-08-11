// IMA ADPCM decode, one invocation per block.
//
// The codec is sequential by construction -- every sample needs the predictor
// the one before it left -- so it looks like the worst possible fit for a GPU.
// It is not, because the stream is cut into *independent* blocks: each one
// restates its own starting predictor, so thousands of them decode at once and
// the sequential part is the few hundred steps inside a single block.
//
// Everything here is integer arithmetic, deliberately. The CPU twin in
// `adpcm.py` runs the identical steps in numpy, and the two are asserted to
// agree **bit for bit** -- a lossy codec that decodes differently depending on
// which route ran would change the audio behind the caller's back.

struct Params {
    blocks : u32,   // how many independent blocks
    block  : u32,   // samples per block
    stride : u32,   // bytes per block, header included
    count  : u32,   // total samples, so the tail block can stop early
};

@group(0) @binding(0) var<uniform>             params : Params;
@group(0) @binding(1) var<storage, read>       body   : array<u32>;
@group(0) @binding(2) var<storage, read_write> samples: array<i32>;

// The IMA step table: 89 quantiser steps, geometric at about 1.1x. Declared
// `private` rather than `const` because it is indexed by a value only known at
// run time.
var<private> STEP : array<i32, 89> = array<i32, 89>(
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41,
    45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190,
    209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724,
    796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272,
    2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132,
    7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350,
    22385, 24623, 27086, 29794, 32767
);

// How the step index moves after each nibble: down for small deltas, up for
// large ones, which is the whole of the "adaptive" in ADPCM.
var<private> INDEX : array<i32, 8> = array<i32, 8>(-1, -1, -1, -1, 2, 4, 6, 8);

// The body arrives as words because that is what a storage buffer holds; the
// format is bytes.
fn byte_at(at : u32) -> u32 {
    return (body[at >> 2u] >> ((at & 3u) * 8u)) & 0xFFu;
}

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid : vec3<u32>) {
    let block = gid.x;
    if (block >= params.blocks) { return; }

    let base = block * params.stride;
    let first = block * params.block;

    // The block header: a verbatim 16-bit sample, then the step index.
    var predictor : i32 = i32(byte_at(base) | (byte_at(base + 1u) << 8u));
    if (predictor > 32767) { predictor = predictor - 65536; }
    var index : i32 = i32(byte_at(base + 2u));

    if (first < params.count) { samples[first] = predictor; }

    for (var step_index : u32 = 1u; step_index < params.block; step_index = step_index + 1u) {
        let out_at = first + step_index;
        if (out_at >= params.count) { return; }

        // Two nibbles to a byte, low nibble first -- the one thing that is
        // silently wrong if you guess it the other way round.
        let nibble_index = step_index - 1u;
        let packed = byte_at(base + 4u + (nibble_index >> 1u));
        var code : i32;
        if ((nibble_index & 1u) == 0u) {
            code = i32(packed & 0x0Fu);
        } else {
            code = i32(packed >> 4u);
        }

        let step = STEP[index];
        let magnitude = code & 7;
        var difference = step >> 3u;
        if ((magnitude & 4) != 0) { difference = difference + step; }
        if ((magnitude & 2) != 0) { difference = difference + (step >> 1u); }
        if ((magnitude & 1) != 0) { difference = difference + (step >> 2u); }

        if ((code & 8) != 0) {
            predictor = predictor - difference;
        } else {
            predictor = predictor + difference;
        }
        predictor = clamp(predictor, -32768, 32767);
        index = clamp(index + INDEX[magnitude], 0, 88);
        samples[out_at] = predictor;
    }
}
