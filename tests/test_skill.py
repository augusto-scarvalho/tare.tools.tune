"""SKILL.md stays true: every command it quotes parses, every lookup runs, the template validates, paths exist."""

import json
import re
import shlex
import sys
from pathlib import Path

import pytest

from tare.tools.tune.cli import main
from tare.tools.tune.dsl.workflow_cli import HELP

ROOT = Path(__file__).resolve().parent.parent
TEXT = (ROOT / "SKILL.md").read_text(encoding="utf-8")
SPANS = re.findall(r"`([^`\n]+)`", TEXT)
sys.path.insert(0, str(ROOT / "tools"))
import curate  # noqa: E402


def usage(run, argv, capsys):
    with pytest.raises(SystemExit):
        run([*argv, "--help"])
    return capsys.readouterr().out


def test_frontmatter_and_size():
    front = TEXT.split("---")[1]
    assert "\nname: tune-game-audio\n" in front and "\ndescription: " in front
    assert ": " not in front.split("description: ", 1)[1]  # a bare colon would break the YAML value
    assert len(TEXT) < 11000, len(TEXT)  # loaded in every session that triggers the skill


@pytest.mark.parametrize("span", [s for s in SPANS if s.startswith(("TUNE ", "CURATE "))])
def test_quoted_commands_exist_with_their_flags(span, capsys):
    words = shlex.split(span)
    tool, words = words[0], words[1:]
    if not words or words[0].startswith("-"):
        return  # `TUNE --help`
    command = words[:2] if tool == "TUNE" and words[0] == "dsl" else words[:1]
    if command == ["dsl", "help"] and len(words) > 2 and not words[2].isupper():
        assert words[2] in HELP
    text = usage(main if tool == "TUNE" else curate.main, command, capsys)
    for flag in (w for w in words if w.startswith("--")):
        assert flag in text, f"{span}: {flag} is not an option of {' '.join(command)}"


@pytest.mark.parametrize("span", [s for s in SPANS if s.startswith("--domain ")])
def test_lookup_rows_run(span, capsys):
    assert main(["dsl", "catalog", *shlex.split(span), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)


def test_template_validates_and_each_kind_materializes(tmp_path, capsys):
    path = tmp_path / "template.tune.json"
    path.write_text(re.search(r"## Template\s+```json\n(.*?)```", TEXT, re.S).group(1), encoding="utf-8")
    assert main(["dsl", "check", str(path), "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["sounds"]) == 7
    for name in ("greet", "hurt", "wolf_attack", "fanfare"):  # speech, vocalization, creature, cue
        assert main(["dsl", "check", str(path), "--expand", "--name", name, "--json"]) == 0
        capsys.readouterr()


def test_quoted_repository_paths_exist():
    paths = set(re.findall(r"\b((?:examples|docs)/[\w./-]*\w)", TEXT))
    assert paths and not [p for p in paths if not (ROOT / p).exists()]
