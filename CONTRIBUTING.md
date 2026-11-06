# Contributing

Thanks for wanting to help. Write in English or Portuguese, whichever you prefer.

## Issues

- **It sounds wrong.** Tell us where (seconds), what you hear and what you expected. Use the "Sounds wrong" form.
  Listening notes are the most useful feedback this project gets: the tests measure sounds, but only ears judge them.
- **Something broke.** Give the command, the error, your OS and Python, and the `.tune.json` if you can share it.
- **An idea.** A sound your game needs, or a workflow that got in your way.

**Never attach a review bundle:** it keeps a copy of any reference recording. Attach the `.tune.json` and the command
instead, and audio only if you have the right to share it.

## Pull requests

They are welcome, and each one is reviewed and approved by the maintainers before it is merged. Open an issue
first for anything bigger than a fix, so we agree on the direction before you write it.

```bash
pip install -e ".[dev,export]" -c constraints.txt     # Python 3.12+, the numpy and scipy every render was verified with
python -m ruff check .
python -m pytest -q -m "not slow"                     # what CI runs; drop -m to include the slow catalogue renders
python tools/build_native.py build                    # optional (C++17 compiler): the C++ renderer is then checked too
```

- **A change to how something sounds changes its samples**, so `tests/test_determinism.py` fails. That is on purpose.
  On Windows, run `python tests/test_determinism.py`: it rewrites only the references that changed and names them.
  Check that each one was meant to change, and say so in the pull request.
- **The frozen fixtures in `tests/fixtures/authoring/` are never regenerated** to make a test pass. A change to renderer
  behavior gets its own version and a written decision; see that folder's README.
- Code, comments, commits and docs are in English. A Portuguese version exists only where it is meant for Portuguese
  readers, such as `README.pt-BR.md` and `docs/pt-BR/`.

## What the project will not take

- AI models at runtime. Models may teach offline, but only their measurements ship.
- Recordings by others in the package or the repository. Recordings are measured, never distributed. Test recordings are
  downloaded by `tools/build_barks.py --download`, and Generation 1 data is yours to supply.
- Samples or data under licences that forbid commercial use or changes, or that are unclear.

## Releases

A release raises the version in `pyproject.toml`, `src/tare/tools/tune/__init__.py` and `.claude-plugin/plugin.json`
together (a test holds them equal), turns the changelog's Unreleased section into that version, and is tagged
`vX.Y.Z`. Plugin users get a new copy only when the version changes.

By contributing you agree that your contribution is licensed under the [Apache License 2.0](LICENSE).
