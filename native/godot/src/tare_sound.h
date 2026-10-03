// Godot classes over the native core: voice banks (.tvb) and the rendering of voice specs from tare.tools.tune.
#pragma once

#include <godot_cpp/classes/audio_stream_wav.hpp>
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/packed_float32_array.hpp>
#include <godot_cpp/variant/string.hpp>

#include "tare_tune.h"

namespace godot {

// A voice bank exported by tare.tools.tune.speech.tvb.export: the frames a planned line is rebuilt from.
class TareVoiceBank : public RefCounted {
    GDCLASS(TareVoiceBank, RefCounted)

    tt_bank *bank_ = nullptr;
    String name_;
    double tract_ = 1.0;
    int64_t frames_ = 0;

protected:
    static void _bind_methods();

public:
    ~TareVoiceBank() override;
    Error load(const String &path);
    String get_bank_name() const { return name_; }
    double get_tract() const { return tract_; }
    int64_t get_frames() const { return frames_; }
    const tt_bank *handle() const { return bank_; }
};

// Renders voice specs from tare.tools.tune (Voice.to_json(): the JSON text, or parsed), with the banks it was given
// for the spoken layers: any sound of the project, the same samples the Python renderer makes. `knobs` turns the
// general knobs over it on the way ({"register": -1, "tempo": 1.5}...), as Python's Sfx(knobs=...) would.
class TareSound : public RefCounted {
    GDCLASS(TareSound, RefCounted)

    Dictionary banks_;   // name -> TareVoiceBank

protected:
    static void _bind_methods();

public:
    void add_bank(const Ref<TareVoiceBank> &bank);
    PackedFloat32Array render_samples(const Variant &spec, int64_t sample_rate, const Dictionary &knobs) const;
    Ref<AudioStreamWAV> render(const Variant &spec, int64_t sample_rate, const Dictionary &knobs) const;
};

}  // namespace godot
