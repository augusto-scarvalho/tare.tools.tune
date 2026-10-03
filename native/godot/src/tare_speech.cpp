#include "tare_speech.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <vector>

#include <godot_cpp/classes/file_access.hpp>
#include <godot_cpp/classes/json.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>
#include <godot_cpp/variant/utility_functions.hpp>

namespace godot {

// -- TareVoiceBank -------------------------------------------------------------------------------------------------

void TareVoiceBank::_bind_methods() {
    ClassDB::bind_method(D_METHOD("load", "path"), &TareVoiceBank::load);
    ClassDB::bind_method(D_METHOD("get_bank_name"), &TareVoiceBank::get_bank_name);
    ClassDB::bind_method(D_METHOD("get_tract"), &TareVoiceBank::get_tract);
    ClassDB::bind_method(D_METHOD("get_frames"), &TareVoiceBank::get_frames);
}

TareVoiceBank::~TareVoiceBank() { tt_bank_free(bank_); }

Error TareVoiceBank::load(const String &path) {
    Ref<FileAccess> f = FileAccess::open(path, FileAccess::READ);
    ERR_FAIL_COND_V_MSG(f.is_null(), ERR_FILE_CANT_OPEN, String("Cannot open the voice bank ") + path);
    ERR_FAIL_COND_V_MSG(f->get_buffer(4).get_string_from_ascii() != String("TVB1"), ERR_FILE_UNRECOGNIZED,
                        path + String(" is not a voice bank (.tvb)"));
    const uint32_t n = f->get_32();
    const Dictionary head = JSON::parse_string(f->get_buffer(n).get_string_from_utf8());
    ERR_FAIL_COND_V_MSG(head.is_empty(), ERR_FILE_CORRUPT, String("Bad header in ") + path);
    const int64_t frames = head["frames"], bands = head["bands"];
    std::vector<float> f0;
    std::vector<uint8_t> env, ap;
    const Array sections = head["sections"];
    for (int64_t i = 0; i < sections.size(); ++i) {
        const Dictionary s = sections[i];
        const int64_t size = s["size"], packed = s["packed"];
        const PackedByteArray raw = f->get_buffer(packed).decompress(size, FileAccess::COMPRESSION_DEFLATE);
        ERR_FAIL_COND_V_MSG(raw.size() != size, ERR_FILE_CORRUPT, String("Bad section in ") + path);
        const String name = s["name"], type = s["type"];
        const uint8_t *p = raw.ptr();
        if (name == "f0") {
            f0.resize(frames);
            std::memcpy(f0.data(), p, frames * sizeof(float));       // little-endian float32, as written
        } else if (name == "env") {
            env.assign(p, p + size);
            if (type == "uint8 delta")                               // each frame stored as its difference to the last
                for (int64_t k = bands; k < size; ++k) env[k] = static_cast<uint8_t>(env[k] + env[k - bands]);
        } else if (name == "ap") {
            ap.assign(p, p + size);
        }
    }
    ERR_FAIL_COND_V_MSG(f0.empty() || env.empty() || ap.empty(), ERR_FILE_CORRUPT,
                        String("Missing frames in ") + path);
    tt_bank_free(bank_);
    bank_ = tt_bank_new(static_cast<int32_t>(frames), static_cast<int32_t>(bands), f0.data(), env.data(), ap.data());
    ERR_FAIL_NULL_V_MSG(bank_, ERR_INVALID_DATA, String("Cannot use the voice bank ") + path);
    name_ = head["name"];
    tract_ = head.get("tract", 1.0);
    frames_ = frames;
    return OK;
}

// -- TareSpeech ----------------------------------------------------------------------------------------------------

void TareSpeech::_bind_methods() {
    ClassDB::bind_method(D_METHOD("add_bank", "bank"), &TareSpeech::add_bank);
    ClassDB::bind_method(D_METHOD("render_samples", "spec", "sample_rate"), &TareSpeech::render_samples,
                         DEFVAL(48000));
    ClassDB::bind_method(D_METHOD("render", "spec", "sample_rate"), &TareSpeech::render, DEFVAL(48000));
}

void TareSpeech::add_bank(const Ref<TareVoiceBank> &bank) {
    ERR_FAIL_COND_MSG(bank.is_null() || !bank->handle(), "Load the voice bank before adding it");
    banks_[bank->get_bank_name()] = bank;
}

PackedFloat32Array TareSpeech::render_samples(const Dictionary &spec, int64_t sample_rate) const {
    const int32_t sr = static_cast<int32_t>(sample_rate);
    const uint64_t seed = static_cast<uint64_t>(static_cast<int64_t>(spec.get("seed", 0)));
    for (const char *other : {"syllables", "chips", "speech", "modal", "noise", "scatter", "vocoded"})
        if (!Array(spec.get(other, Array())).is_empty())
            UtilityFunctions::push_warning(String("tare.tools.tune: only spoken layers render here; skipping ") +
                                           String(other));
    for (const char *other : {"room", "air", "lowpass", "loop", "space"})
        if (static_cast<double>(spec.get(other, 0.0)) != 0.0)
            UtilityFunctions::push_warning(String("tare.tools.tune: '") + String(other) +
                                           String("' is left to the engine here"));

    std::vector<std::pair<int64_t, std::vector<double>>> parts;
    const Array layers = spec.get("spoken", Array());
    for (int64_t i = 0; i < layers.size(); ++i) {
        const Dictionary layer = layers[i];
        const String bank_name = layer["bank"];
        const Ref<TareVoiceBank> bank = banks_.get(bank_name, Variant());
        ERR_FAIL_COND_V_MSG(bank.is_null(), PackedFloat32Array(),
                            String("No voice bank ") + bank_name + String(" was added"));
        const Array pieces = layer["pieces"], joins_a = layer.get("joins", Array()), f0_a = layer["f0"];
        std::vector<double> p(3 * pieces.size()), f0(f0_a.size());
        std::vector<int32_t> joins(joins_a.size());
        for (int64_t k = 0; k < pieces.size(); ++k) {
            const Array piece = pieces[k];
            for (int c = 0; c < 3; ++c) p[3 * k + c] = piece[c];
        }
        for (int64_t k = 0; k < joins_a.size(); ++k) joins[k] = static_cast<int32_t>(static_cast<int64_t>(joins_a[k]));
        for (int64_t k = 0; k < f0_a.size(); ++k) f0[k] = f0_a[k];
        double *out = nullptr;
        int32_t n = 0;
        const int32_t status = tt_render_spoken(
            bank->handle(), p.data(), static_cast<int32_t>(pieces.size()), joins.data(),
            static_cast<int32_t>(joins.size()), f0.data(), static_cast<int32_t>(f0.size()), layer.get("warp", 1.0),
            layer.get("breath", 0.0), layer.get("tilt", 0.0), layer.get("gain", 1.0),
            tt_key(seed, "spoken", i), sr, &out, &n);
        ERR_FAIL_COND_V_MSG(status != 0, PackedFloat32Array(), "Cannot render a spoken layer");
        const double start = layer.get("start", 0.0);
        parts.emplace_back(static_cast<int64_t>(start * sr), std::vector<double>(out, out + n));
        tt_free(out);
    }
    ERR_FAIL_COND_V_MSG(parts.empty(), PackedFloat32Array(), "The spec has no spoken layers");
    int64_t length = 0;
    for (const auto &[at, y] : parts) length = std::max<int64_t>(length, at + static_cast<int64_t>(y.size()));
    std::vector<double> mix(length, 0.0);
    for (const auto &[at, y] : parts)
        for (size_t k = 0; k < y.size(); ++k) mix[at + k] += y[k];
    tt_finish(mix.data(), static_cast<int32_t>(length), sr, spec.get("gain", 1.0), spec.get("crush", 0.0),
              spec.get("drive", 0.0));
    PackedFloat32Array samples;
    samples.resize(length);
    float *w = samples.ptrw();
    for (int64_t k = 0; k < length; ++k) w[k] = static_cast<float>(mix[k]);
    return samples;
}

Ref<AudioStreamWAV> TareSpeech::render(const Dictionary &spec, int64_t sample_rate) const {
    const PackedFloat32Array samples = render_samples(spec, sample_rate);
    PackedByteArray data;
    data.resize(samples.size() * 2);
    uint8_t *w = data.ptrw();
    for (int64_t k = 0; k < samples.size(); ++k) {
        const auto v = static_cast<int16_t>(std::lrint(std::clamp(samples[k], -1.0f, 1.0f) * 32767.0f));
        w[2 * k] = static_cast<uint8_t>(v & 0xFF);
        w[2 * k + 1] = static_cast<uint8_t>((v >> 8) & 0xFF);
    }
    Ref<AudioStreamWAV> stream;
    stream.instantiate();
    stream->set_format(AudioStreamWAV::FORMAT_16_BITS);
    stream->set_mix_rate(static_cast<int32_t>(sample_rate));
    stream->set_stereo(false);
    stream->set_data(data);
    return stream;
}

}  // namespace godot
