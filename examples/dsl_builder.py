"""Build a reusable bank as inspectable JSON data, without executable project files."""

from tare.tools.tune.dsl import Project, definition, param, sfx, use

confirm = definition(
    sfx("ui", style="crystal", event="confirm", species=7, power=param("power"), dry=True),
    params={"power": {"type": "number", "default": 0.5, "min": 0, "max": 1}},
)
project = Project(
    context={"sample_rate": 16000},
    defs={"confirm": confirm},
    sounds={"quiet": use("confirm", power=0.3), "strong": use("confirm", power=0.8)},
)

if __name__ == "__main__":
    project.write("authoring-out/builder.tune.json")
