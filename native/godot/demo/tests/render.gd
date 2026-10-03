# Renders voice specs with the extension, for tests/test_godot.py:
#   godot --headless --path native/godot/demo --script res://tests/render.gd -- <out dir> <sample rate> <files...>
# Every .tvb given is loaded as a voice bank; every .json spec is rendered to <out dir>/<name>.f32 (float32 samples)
# from its parsed Dictionary, and to <name>.text.f32 from its JSON text.
extends SceneTree


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var out_dir: String = args[0]
	var sample_rate := int(args[1])
	var sound := TareSound.new()
	for path in args.slice(2):
		if path.ends_with(".tvb"):
			var bank := TareVoiceBank.new()
			if bank.load(path) != OK:
				quit(1)
				return
			sound.add_bank(bank)
	for path in args.slice(2):
		if path.ends_with(".json"):
			var text := FileAccess.get_file_as_string(path)
			var base := path.get_file().get_basename()
			for spec in [JSON.parse_string(text), text]:
				var samples: PackedFloat32Array = sound.render_samples(spec, sample_rate)
				var f := FileAccess.open(out_dir.path_join(base + (".text" if spec is String else "") + ".f32"),
						FileAccess.WRITE)
				f.store_buffer(samples.to_byte_array())
	quit(0)
