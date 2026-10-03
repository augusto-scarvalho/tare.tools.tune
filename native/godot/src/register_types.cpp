#include <gdextension_interface.h>

#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/core/defs.hpp>
#include <godot_cpp/godot.hpp>

#include "tare_speech.h"

using namespace godot;

static void initialize_tare_tune(ModuleInitializationLevel level) {
    if (level != MODULE_INITIALIZATION_LEVEL_SCENE) return;
    GDREGISTER_CLASS(TareVoiceBank);
    GDREGISTER_CLASS(TareSpeech);
}

static void uninitialize_tare_tune(ModuleInitializationLevel) {}

extern "C" {

GDExtensionBool GDE_EXPORT tare_tune_library_init(GDExtensionInterfaceGetProcAddress get_proc_address,
                                                  const GDExtensionClassLibraryPtr library,
                                                  GDExtensionInitialization *initialization) {
    GDExtensionBinding::InitObject init(get_proc_address, library, initialization);
    init.register_initializer(initialize_tare_tune);
    init.register_terminator(uninitialize_tare_tune);
    init.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);
    return init.init();
}

}
