# Style and validation
- Python project using type hints and dataclasses/Pydantic heavily.
- Existing formatting/linting uses Ruff (`ruff check`, `ruff format`), with target line length 100.
- Tests are pytest-based; OpenArm/nanobot coverage lives in dedicated test files under `tests/`.
- Important current validation caveat: `uv run pytest ...` currently fails if `capx/third_party/sam3` is not populated because `pyproject.toml` declares it as an editable source. In this workspace `.venv` also lacks `pytest`.