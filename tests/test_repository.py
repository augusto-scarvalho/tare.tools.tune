"""The public repository stays clean: links resolve, the two READMEs match, and nothing personal or recorded ships."""
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
try:
    TRACKED = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.splitlines()
except (OSError, subprocess.CalledProcessError):
    TRACKED = []
pytestmark = pytest.mark.skipif(not TRACKED, reason="not a git checkout")
TEXT = (".md", ".py", ".json", ".toml", ".txt", ".yml", ".yaml", ".cpp", ".h", ".gd", ".html", ".js", ".css", ".csv")
LINK = re.compile(r"\]\(([^)\s]+)[^)]*\)|(?:src|href)=\"([^\"]+)\"")


def text_files():
    return [f for f in TRACKED if f.endswith(TEXT)]


def test_markdown_links_resolve():
    broken = []
    for f in TRACKED:
        if not f.endswith(".md") or f.startswith("docs/plans/"):   # plans quote text meant for other files
            continue
        text = re.sub(r"```.*?```", "", (ROOT / f).read_text(encoding="utf-8"), flags=re.S)
        for m in LINK.finditer(text):
            target = (m.group(1) or m.group(2)).split("#")[0]
            if target and not re.match(r"[a-z]+:", target) and not (ROOT / f).parent.joinpath(target).exists():
                broken.append(f"{f}: {target}")
    assert not broken


def test_readmes_match():
    en, pt = ((ROOT / f).read_text(encoding="utf-8") for f in ("README.md", "README.pt-BR.md"))
    assert len(re.findall(r"^## ", en, re.M)) == len(re.findall(r"^## ", pt, re.M))
    assert "README.pt-BR.md" in en and "README.md" in pt


def test_nothing_personal():
    # a home folder names its user; a session link opens a private conversation
    personal = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+\w|/home/\w|/Users/\w|claude\.ai/code/session_")
    found = [f for f in text_files() if personal.search((ROOT / f).read_text(encoding="utf-8", errors="replace"))]
    assert not found


def test_no_recordings_in_the_repository():
    # sounds people hear come from releases; the only audio file is a test fixture made by tune itself
    audio = [f for f in TRACKED if f.lower().endswith((".wav", ".ogg", ".mp3", ".flac", ".m4a"))]
    assert all(f.startswith("tests/fixtures/") for f in audio), audio


def test_one_version_everywhere():
    # the Claude Code plugin caches one copy per version: users get changes only when it moves
    project = re.search(r'^version = "(.+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)[1]
    init = (ROOT / "src/tare/tools/tune/__init__.py").read_text(encoding="utf-8")
    package = re.search(r'__version__ = "(.+)"', init)[1]
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    assert project == package == plugin
    assert f"## {project} (" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
