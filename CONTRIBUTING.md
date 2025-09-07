# Contributing

## Setup

Requirements:
- Python 3.13+
- Conda
- Git

Development setup:

```bash
git clone https://github.com/yourusername/zulip-refinement-bot.git
cd zulip-refinement-bot
conda env create -f environment.yml
conda activate zulip-refinement-bot
pip install -e ".[dev,test]"
pre-commit install
```

Verify setup:
```bash
pytest
zulip-refinement-bot --help
```

## Workflow

1. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make changes with tests

3. Run tests and linting:
   ```bash
   pytest
   pytest --cov=src/zulip_refinement_bot --cov-report=html
   ruff check src/ tests/
   ruff format --check src/ tests/
   mypy src/
   ```

4. Commit using conventional commits:
   ```bash
   git commit -m "feat: add estimation voting functionality"
   ```

Commit types:
- `feat:` - New features
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `refactor:` - Code refactoring
- `test:` - Adding or updating tests

5. Push and create pull request:
   ```bash
   git push origin feature/your-feature-name
   ```

## Code Standards

- Use ruff for formatting and linting (100 char line limit)
- Type hints required for all functions
- Tests required for new features
- Docstrings for public APIs


## Testing

Write tests for all new functionality using pytest:

```python
def test_create_batch():
    # Arrange
    db_manager = DatabaseManager(":memory:")

    # Act
    batch_id = db_manager.create_batch("2024-01-01", "2024-01-03", "Test User")

    # Assert
    assert isinstance(batch_id, int)
    assert batch_id > 0
```

Use markers to categorize tests:
```bash
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m "not slow"    # Skip slow tests
```

## Documentation

- Add docstrings for public functions
- Update README for new features
- Include type hints

## Bug Reports

Include:
- Python version and OS
- Steps to reproduce
- Full error messages
- Configuration used

## Feature Requests

- Check existing issues first
- Describe the use case
- Provide usage examples

## Pull Requests

Before submitting:
- Tests pass (`pytest`)
- Code formatted (`ruff`)
- Type checking passes (`mypy`)
- Documentation updated
