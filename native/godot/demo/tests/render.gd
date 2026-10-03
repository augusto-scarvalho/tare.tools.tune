# Renders voice specs with the extension, for tests/test_godot.py:
#   godot --headless --path native/godot/demo --script res://tests/render.gd -- <out dir> <sample rate> <files...>
# Every .tvb given is loaded as a voice bank; every .json spec is rendered to <out dir>/<name>.f32 (float32 samples).
extends SceneTree


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var out_dir: String = args[0]
	var sample_rate := int(args[1])
	var speech := TareSpeech.new()
	for path in args.slice(2):
		if path.ends_with(".tvb"):
			var bank := TareVoiceBank.new()
			if bank.load(path) != OK:
				quit(1)
				return
			speech.add_bank(bank)
	for path in args.slice(2):
		if path.ends_with(".json"):
			var spec = JSON.parse_string(FileAccess.get_file_as_string(path))
			var samples: PackedFloat32Array = speech.render_samples(spec, sample_rate)
			var f := FileAccess.open(out_dir.path_join(path.get_file().get_basename() + ".f32"), FileAccess.WRITE)
			f.store_buffer(samples.to_byte_array())
	quit(0)
