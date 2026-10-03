#include "tare_sound.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <vector>

#include <godot_cpp/classes/file_access.hpp>
#include <godot_cpp/classes/json.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>

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

// -- TareSound -----------------------------------------------------------------------------------------------------

void TareSound::_bind_methods() {
    ClassDB::bind_method(D_METHOD("add_bank", "bank"), &TareSound::add_bank);
    ClassDB::bind_method(D_METHOD("render_samples", "spec", "sample_rate"), &TareSound::render_samples,
                         DEFVAL(48000));
    ClassDB::bind_method(D_METHOD("render", "spec", "sample_rate"), &TareSound::render, DEFVAL(48000));
}

void TareSound::add_bank(const Ref<TareVoiceBank> &bank) {
    ERR_FAIL_COND_MSG(bank.is_null() || !bank->handle(), "Load the voice bank before adding it");
    banks_[bank->get_bank_name()] = bank;
}

static String spec_text(const Variant &spec) {
    return spec.get_type() == Variant::STRING ? String(spec) : JSON::stringify(spec, "", false, true);
}

PackedFloat32Array TareSound::render_samples(const Variant &spec, int64_t sample_rate) const {
    ERR_FAIL_COND_V_MSG(spec.get_type() != Variant::STRING && spec.get_type() != Variant::DICTIONARY,
                        PackedFloat32Array(), "A voice spec is its JSON text or the parsed Dictionary");
    const CharString json = spec_text(spec).utf8();
    std::vector<const tt_bank *> handles;
    std::vector<CharString> names;
    const Array keys = banks_.keys();
    for (int64_t i = 0; i < keys.size(); ++i) {
        const Ref<TareVoiceBank> bank = banks_[keys[i]];
        handles.push_back(bank->handle());
        names.push_back(String(keys[i]).utf8());
    }
    std::vector<const char *> name_ptrs;
    for (const CharString &n : names) name_ptrs.push_back(n.get_data());
    float *out = nullptr;
    int32_t n = 0;
    const int32_t status = tt_render_voice(json.get_data(), handles.data(), name_ptrs.data(),
                                           static_cast<int32_t>(handles.size()), static_cast<int32_t>(sample_rate),
                                           &out, &n);
    ERR_FAIL_COND_V_MSG(status != 0, PackedFloat32Array(),
                        String("tare.tools.tune: ") + String::utf8(tt_last_error()));
    PackedFloat32Array samples;
    samples.resize(n);
    std::memcpy(samples.ptrw(), out, static_cast<size_t>(n) * sizeof(float));
    tt_free(out);
    return samples;
}

Ref<AudioStreamWAV> TareSound::render(const Variant &spec, int64_t sample_rate) const {
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
    const Dictionary fields = spec.get_type() == Variant::STRING ? Dictionary(JSON::parse_string(spec)) : Dictionary(spec);
    if (static_cast<double>(fields.get("loop", 0.0)) > 0) {   // rendered as a seamless loop: play it as one
        stream->set_loop_mode(AudioStreamWAV::LOOP_FORWARD);
        stream->set_loop_begin(0);
        stream->set_loop_end(samples.size());
    }
    return stream;
}

}  // namespace godot
