# Contributing

## Setup

```bash
uv sync
uv pip install -e .
```

## Development

```bash
# Run locally
uv run ghaw-auditor scan --repo .

# Tests
uv run -m pytest
uv run -m pytest -k test_name

# Coverage
uv run -m pytest --cov --cov-report=html

# Lint & format
uvx ruff check .
uvx ruff format .

# Type check
uvx mypy .
```

## Code Style

- Python 3.11+ with type hints
- Max line length: 120 characters
- Follow PEP 8
- Use Pydantic for models
- Add docstrings to public functions

## Testing

- Write tests for new features
- Maintain coverage ≥ 85%
- Use pytest fixtures
- Mock external API calls

## Pull Requests

1. Fork and create a feature branch
2. Add tests
3. Ensure all checks pass
4. Update CHANGELOG.md
5. Submit PR with clear description

## Commit Messages

Follow conventional commits:

- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation
- `test:` tests
- `refactor:` code refactoring

## Questions?

Open an issue for discussion.
