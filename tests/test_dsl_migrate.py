import json
from pathlib import Path

import pytest

from tare.tools.tune.dsl import DSLError, load
from tare.tools.tune.dsl.migrate import freeze, migrate, variants


def test_migrate_preserves_score_pcm_and_original(tmp_path):
    original = Path(__file__).parent.parent / "examples/authoring.json"
    before = original.read_bytes()
    output = tmp_path / "score.tune.json"
    result = migrate(original, output)
    assert result["equivalent"] and result["sounds"][0]["pcm_equal"]
    assert original.read_bytes() == before
    assert load(output).data["sounds"]["authoring"]["score"]["loop"] == "1bar"
    with pytest.raises(DSLError, match="new output"):
        migrate(original, original)


def test_freeze_capabilities_and_explicit_variants(tmp_path):
    root = Path(__file__).parent.parent
    result = freeze(
        root / "examples/dsl-bank.tune.json", tmp_path / "confirm.voice.json", name="confirm", format="voice"
    )
    assert result["kind"] == "voice"
    assert json.loads((tmp_path / "confirm.voice.json").read_text())["format"] == "tare.tools.tune.voice"
    with pytest.raises(DSLError, match="PCM"):
        freeze(root / "examples/dsl-music.tune.json", tmp_path / "bad.voice.json", format="voice")
    generated = variants(
        root / "examples/dsl-bank.tune.json", tmp_path / "variants.tune.json", "confirm", "power", [0.2, 0.8]
    )
    assert generated["sounds"] == ["confirm_0", "confirm_1"]
