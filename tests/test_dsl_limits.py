import pytest
from test_dsl_loading import project

from tare.tools.tune.dsl import Budgets, DSLError, compile_document, load


@pytest.mark.parametrize(
    "expression",
    [
        {"voice": [{"syllable": {"start": 0, "dur": 0.2, "pitch": [], "source": "sine"}}]},
        {"voice": [{"noise": {"start": 0, "dur": 0.2, "freq": [[1, 400], [0, 200]]}}]},
        {"voice": [{"modal": {"start": 0, "dur": 0.2, "modes": [[0, 0.1, 1]]}}]},
        {"voice": [{"spoken": {"bank": "pt\\..\\private", "pieces": [[0, 1, 2]], "f0": [100, 100]}}]},
        {"score": {"effects": [{"type": "limiter"}, {"type": "chorus"}]}},
        {"score": {"effects": [{"type": "chorus", "voices": True}]}},
        {"score": {"tracks": [{"name": "lead", "voice": {"seed": 7}}]}},
        {"score": {"tracks": [{"name": "lead", "instrument": "harp", "notes": {"notes": [[[], 0, 1]]}}]}},
        {"sfx": "ui", "dry": "yes"},
        {"fm": {"freq": 440, "duration": 0.2, "index": float("inf")}},
    ],
)
def test_invalid_physical_values_fail_before_render(expression):
    with pytest.raises(DSLError):
        compile_document(load(data=project(expression)))


def test_cumulative_note_layer_and_memory_budgets():
    song = {
        "score": {
            "tracks": [
                {
                    "name": "a",
                    "instrument": "harp",
                    "notes": {"repeat": 4, "of": {"pattern": "C4 C4 C4 C4", "steps": 4}},
                }
            ]
        }
    }
    with pytest.raises(DSLError, match="notes"):
        compile_document(load(data=project(song), limits=Budgets(notes=10)))
    with pytest.raises(DSLError, match="memory"):
        compile_document(load(data=project({"fm": {"duration": 3}}), limits=Budgets(work_bytes=1000)))
    with pytest.raises(DSLError, match="layers"):
        compile_document(load(data=project({"sfx": "ui"}), limits=Budgets(layers=0)))


def test_signed_gain_cancellation_is_preserved():
    primitive = {"start": 0, "dur": 0.1, "pitch": [[0, 220]], "source": "sine"}
    expression = {"voice": [{"syllable": primitive | {"gain": 1}}, {"syllable": primitive | {"gain": -1}}]}
    from tare.tools.tune.dsl.composition import capture_plan

    result = capture_plan(compile_document(load(data=project(expression))).plan)
    assert not result.audio.any()


@pytest.mark.parametrize(
    "layer",
    [
        {"modal": {"start": 0, "dur": 0.1, "modes": [[440, 0.1, 1]], "hits": [[0, 1, 1e12]]}},
        {"modal": {"start": 0, "dur": 0.1, "modes": [[440, 0.1, 1]], "scrape": [0, 1e12, 1, 0]}},
        {"scatter": {"start": 0, "dur": 0.1, "rate": [[0, 1e12]]}},
    ],
)
def test_nested_work_cross_products_are_rejected_before_any_synthesis(layer):
    with pytest.raises(DSLError) as failed:
        compile_document(load(data=project({"voice": [layer]})))
    assert failed.value.code == "E_LIMIT"


def test_weighted_mode_budget_and_score_duration_are_checked_without_render():
    expression = {"voice": [{"modal": {"start": 0, "dur": 0.1, "modes": [[440, 0.1, 1]] * 256}}]}
    with pytest.raises(DSLError, match="weighted_work"):
        compile_document(load(data=project(expression), limits=Budgets(weighted_work=10000)))
    with pytest.raises(DSLError, match="duration"):
        compile_document(
            load(
                data=project(
                    {"score": {"tracks": [{"name": "late", "instrument": "harp", "notes": {"notes": [[60, 1000, 1]]}}]}}
                )
            )
        )


def test_pcm_byte_budget_is_checked_from_header_before_decoding(tmp_path, monkeypatch):
    import wave

    import numpy as np

    from tare.tools.tune.audio_io import write_wav

    path = tmp_path / "audio.wav"
    write_wav(path, np.zeros((1000, 2), np.float32), 16000)
    original = wave.Wave_read.readframes
    reads = []

    def spy(self, frames):
        reads.append(frames)
        return original(self, frames)

    monkeypatch.setattr(wave.Wave_read, "readframes", spy)
    with pytest.raises(DSLError) as failed:
        compile_document(
            load(tmp_path / "bank.tune.json", data=project({"audio": "audio.wav"}), limits=Budgets(capture_bytes=1000))
        )
    assert failed.value.code == "E_LIMIT" and reads == []


def test_semantic_speech_limits_apply_before_frame_program_generation(monkeypatch):
    from tare.tools.tune.speech import Speaker

    calls = []
    monkeypatch.setattr(Speaker, "voice", lambda *args, **kwargs: calls.append(True))
    for expression in ({"say": "a" * 1025}, {"say": "Hi", "speaker": {"speaker": "default", "rate": 1e-8}}):
        with pytest.raises(DSLError):
            compile_document(load(data=project(expression)))
    assert calls == []
