# A dialogue voiced in the game: the lines were planned in Python (lines/*.json, tare.tools.tune specs) and are
# rendered here by the native renderer from the voice banks (voices/*.tvb), in a thread, the next while one plays.
# The click that advances it is a spec too (sounds/advance.json), rendered once at start.
extends Control

var sound := TareSound.new()
var lines: Array = []
var current := -1
var next_stream: AudioStreamWAV
var worker := Thread.new()

@onready var label := Label.new()
@onready var player := AudioStreamPlayer.new()
@onready var click := AudioStreamPlayer.new()


func _ready() -> void:
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	label.add_theme_font_size_override("font_size", 28)
	add_child(label)
	add_child(player)
	add_child(click)
	for file in DirAccess.get_files_at("res://voices"):
		if file.ends_with(".tvb"):
			var bank := TareVoiceBank.new()
			if bank.load("res://voices/" + file) == OK:
				sound.add_bank(bank)
	lines = JSON.parse_string(FileAccess.get_file_as_string("res://lines/dialogue.json"))
	click.stream = sound.render(FileAccess.get_file_as_string("res://sounds/advance.json"), 48000)
	label.text = "(clique ou espaço para começar)"
	worker.start(_render.bind(0))


func _render(index: int) -> AudioStreamWAV:
	return sound.render(FileAccess.get_file_as_string("res://lines/" + lines[index]["spec"]), 48000)


func _unhandled_input(event: InputEvent) -> void:
	var pressed: bool = event is InputEventMouseButton and event.pressed
	pressed = pressed or (event is InputEventKey and event.pressed and event.keycode == KEY_SPACE)
	if pressed and current + 1 < lines.size():
		current += 1
		click.play()
		var stream: AudioStreamWAV = worker.wait_to_finish()
		label.text = "%s: %s" % [lines[current]["speaker"], lines[current]["text"]]
		player.stream = stream
		player.play()
		if current + 1 < lines.size():
			worker.start(_render.bind(current + 1))


func _exit_tree() -> void:
	if worker.is_started():
		worker.wait_to_finish()
