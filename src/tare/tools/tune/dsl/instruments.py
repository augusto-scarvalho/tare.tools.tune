"""Finite affine Note templates evaluated by the existing Track.play exactly once."""

import copy

from .adapters import make_layer
from .model import DSLError
from .validate import choice, known, number


def chip(data, at):
    """A chip channel as a track instrument: the same arguments as instruments.chip_voice, checked."""
    from ..instruments import DUTIES, chip_voice

    vibrato = data.get("vibrato", [0, 0])
    if not isinstance(vibrato, list) or len(vibrato) != 2:
        raise DSLError("E_TYPE", "vibrato is [Hz, semitones]", at + "/vibrato")
    if type(data.get("fade", False)) is not bool:
        raise DSLError("E_TYPE", "fade is true or false", at + "/fade")
    return chip_voice(
        choice(data["chip_voice"], ("pulse", "triangle"), at + "/chip_voice"),
        choice(data.get("duty", 25), DUTIES, at + "/duty"),
        (number(vibrato[0], at + "/vibrato", 0, 30), number(vibrato[1], at + "/vibrato", 0, 2)),
        number(data.get("slide", 0), at + "/slide", -24, 24),
        data.get("fade", False),
    )


class Template:
    def __init__(self, node, compiler):
        self.node, self.compiler = node, compiler
        self.midi_program = node.data.get("midi_program")
        if self.midi_program is not None:
            number(self.midi_program, node.origin["pointer"], 0, 127, integer=True)
        # Name is provenance only; Note/render seeds do not consume it.
        from ..diagnostics import digest

        self.__qualname__ = "template_" + digest(node.data)[:12]

    def __call__(self, note):
        def fill(value):
            if isinstance(value, dict):
                if "note" in value:
                    known(value, {"note", "scale", "offset"})
                    if value["note"] not in ("start", "dur", "f", "vel"):
                        raise DSLError("E_SLOT", "unknown Note slot")
                    return getattr(note, value["note"]) * number(value.get("scale", 1)) + number(value.get("offset", 0))
                if "rand" in value:
                    known(value, {"rand", "min", "max"})
                    if not isinstance(value["rand"], str):
                        raise DSLError("E_SLOT", "random stream needs a string name")
                    low, high = number(value.get("min", 0)), number(value.get("max", 1))
                    if high < low:
                        raise DSLError("E_RANGE", "random upper bound is below lower bound")
                    return low + (high - low) * note.rand("dsl:" + value["rand"])
                return {key: fill(child) for key, child in value.items()}
            if isinstance(value, list):
                return [fill(child) for child in value]
            return value

        output = []
        for child in self.node.children["items"]:
            while child.op == "use":
                child = child.children["body"]
            self.compiler.budget.charge("layers", 1, child.origin["pointer"])
            if child.op not in ("syllable", "modal", "noise", "scatter", "chip"):
                raise DSLError("E_CAPABILITY", "Track supports syllable/modal/noise/scatter/chip templates")
            value = make_layer(
                child.op, fill(copy.deepcopy(child.data[child.op])), child.origin, self.node.context["sample_rate"]
            )
            output.append(value.value)
        return output
