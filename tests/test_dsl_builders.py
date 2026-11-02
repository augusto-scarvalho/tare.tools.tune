import copy

import numpy as np
import pytest

from tare.tools.tune.dsl import DSLError, Project, definition, fm, mix, param, pattern, sfx, transpose, use
from tare.tools.tune.dsl.composition import capture_plan


def test_builders_are_immutable_data_and_match_file_compilation(tmp_path):
    expression = sfx("ui", style="crystal", event="confirm", power=param("power"), dry=True)
    params = {"power": {"type": "number", "default": 0.5, "min": 0, "max": 1}}
    bank = Project(
        defs={"confirmation": definition(expression, params=params)},
        context={"sample_rate": 16000},
        sounds={"a": use("confirmation", power=0.8)},
    )
    before = copy.deepcopy(bank.to_dict())
    params["power"]["default"] = 0.2
    assert bank.to_dict() == before
    artifact = bank.to_dict()
    artifact["sounds"].clear()
    assert bank.to_dict() == before
    restored = Project.from_dict(bank.to_dict())
    assert restored.to_dict() == before
    path = tmp_path / "bank.tune.json"
    bank.write(path)
    from tare.tools.tune.dsl import build_file

    direct = capture_plan(bank.compile(path=path).plan)
    assert np.array_equal(build_file(path).audio, direct.audio)


def test_transform_builders_do_not_mutate_notes_and_reject_python_objects():
    a = pattern("C4 - . .")
    b = a.then(transpose(12))
    assert "then" not in a.to_dict() and b.to_dict()["then"] == [{"transpose": 12}]
    with pytest.raises(DSLError, match="JSON data"):
        Project(sounds={"a": lambda: None})
    with pytest.raises(DSLError):
        Project(sounds={"a": np.zeros(20)})


def test_semantic_and_fm_mix_keeps_pcm_boundary():
    bank = Project(
        context={"sample_rate": 16000},
        sounds={
            "a": mix(
                {"sound": sfx("blade", style="steel", species=7, dry=True), "gain": 0.5},
                {"at": "20ms", "sound": fm(freq=110, ratio=1, index=2, duration=0.2), "gain": 0.1},
            )
        },
    )
    result = bank.compile()
    assert not result.summary()["capabilities"]["voice_json"]
    assert capture_plan(result.plan).manifest["schema"] == 2
