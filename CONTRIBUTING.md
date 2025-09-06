# Contributing to Zulip Refinement Bot

Thank you for your interest in contributing to the Zulip Refinement Bot! This document provides guidelines and information for contributors.

## 🚀 Getting Started

### Prerequisites

- Python 3.11 or higher
- Conda or Miniconda
- Git
- Docker (optional, for testing containerization)

### Development Setup

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/yourusername/zulip-refinement-bot.git
   cd zulip-refinement-bot
   ```

2. **Create conda environment**
   ```bash
   conda env create -f environment.yml
   conda activate zulip-refinement-bot
   ```

3. **Install in development mode**
   ```bash
   pip install -e ".[dev,test]"
   ```

4. **Install pre-commit hooks**
   ```bash
   pre-commit install
   ```

5. **Verify setup**
   ```bash
   pytest
   zulip-refinement-bot --help
   ```

## 🧪 Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
```

Use descriptive branch names:
- `feature/add-estimation-voting`
- `bugfix/fix-github-api-timeout`
- `docs/update-installation-guide`

### 2. Make Your Changes

- Write code following our [coding standards](#-coding-standards)
- Add tests for new functionality
- Update documentation as needed
- Ensure all tests pass

### 3. Test Your Changes

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/zulip_refinement_bot --cov-report=html

# Run linting and formatting
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/

# Run all pre-commit hooks
pre-commit run --all-files
```

### 4. Commit Your Changes

We use [Conventional Commits](https://www.conventionalcommits.org/):

```bash
git add .
git commit -m "feat: add estimation voting functionality"
```

Commit types:
- `feat:` - New features
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting, etc.)
- `refactor:` - Code refactoring
- `test:` - Adding or updating tests
- `chore:` - Maintenance tasks

### 5. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub with:
- Clear title and description
- Reference any related issues
- Include screenshots for UI changes
- Add appropriate labels

## 📏 Coding Standards

### Code Style

- **Ruff** for code formatting and linting (line length: 100)
- **mypy** for type checking

### Code Quality Requirements

- ✅ **100% test coverage** for new features
- 📝 **Type hints** for all function parameters and returns
- 📚 **Docstrings** for all public functions and classes
- 🏷️ **Descriptive variable and function names**
- 🧪 **Unit tests** for all new functionality
- 🔍 **Integration tests** for complex workflows

### Example Code Style

```python
"""Module docstring describing the purpose."""

from __future__ import annotations

from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class ExampleClass:
    """Class docstring describing the purpose and usage."""

    def __init__(self, config: Config) -> None:
        """Initialize the class.

        Args:
            config: Configuration object
        """
        self.config = config

    def process_data(self, data: str) -> Optional[str]:
        """Process input data and return result.

        Args:
            data: Input data to process

        Returns:
            Processed data or None if processing fails

        Raises:
            ValueError: If data is invalid
        """
        if not data:
            raise ValueError("Data cannot be empty")

        logger.info("Processing data", data_length=len(data))
        return data.upper()
```

## 🧪 Testing Guidelines

### Test Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── test_config.py           # Configuration tests
├── test_database.py         # Database tests
├── test_github_api.py       # GitHub API tests
├── test_parser.py           # Input parsing tests
├── test_bot.py              # Main bot tests
└── integration/             # Integration tests
    └── test_full_workflow.py
```

### Writing Tests

1. **Use descriptive test names**
   ```python
   def test_parse_batch_input_with_valid_github_urls():
       """Test parsing valid GitHub URLs in batch input."""
   ```

2. **Follow AAA pattern** (Arrange, Act, Assert)
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

3. **Use fixtures for common setup**
   ```python
   @pytest.fixture
   def sample_config():
       return Config(
           zulip_email="test@example.com",
           zulip_api_key="test_key",
           zulip_site="https://test.zulipchat.com"
       )
   ```

4. **Mock external dependencies**
   ```python
   @patch('zulip_refinement_bot.github_api.httpx.Client')
   def test_github_api_success(mock_client):
       # Test implementation
   ```

### Test Categories

Use pytest markers to categorize tests:

```python
@pytest.mark.unit
def test_config_validation():
    """Unit test for configuration validation."""

@pytest.mark.integration
def test_full_batch_workflow():
    """Integration test for complete batch workflow."""

@pytest.mark.slow
def test_large_dataset_processing():
    """Slow test that processes large datasets."""
```

Run specific test categories:
```bash
pytest -m unit          # Only unit tests
pytest -m "not slow"    # Skip slow tests
pytest -m integration   # Only integration tests
```

## 📚 Documentation

### Code Documentation

- **Docstrings**: All public functions, classes, and modules
- **Type hints**: All function parameters and return values
- **Comments**: Complex logic and business rules
- **README updates**: For new features or configuration changes

### Documentation Style

Use Google-style docstrings:

```python
def fetch_issue_title(self, owner: str, repo: str, issue_number: str) -> Optional[str]:
    """Fetch issue title from GitHub API.

    Args:
        owner: Repository owner (e.g., 'conda')
        repo: Repository name (e.g., 'conda')
        issue_number: Issue number as string

    Returns:
        Issue title if successful, None if failed

    Raises:
        ValueError: If parameters are invalid

    Example:
        >>> api = GitHubAPI()
        >>> title = api.fetch_issue_title("conda", "conda", "15169")
        >>> print(title)
        "Fix memory leak in solver"
    """
```

## 🐛 Bug Reports

When reporting bugs, please include:

1. **Environment information**
   - Python version
   - Operating system
   - Package versions (`pip freeze` or `conda list`)

2. **Steps to reproduce**
   - Minimal code example
   - Configuration used
   - Expected vs actual behavior

3. **Error messages**
   - Full stack traces
   - Log output (with sensitive data removed)

4. **Additional context**
   - Screenshots if applicable
   - Related issues or PRs

## 💡 Feature Requests

For new features, please:

1. **Check existing issues** to avoid duplicates
2. **Describe the use case** and motivation
3. **Provide examples** of how it would be used
4. **Consider backwards compatibility**
5. **Discuss implementation approach** if you have ideas

## 🔄 Pull Request Process

### Before Submitting

- [ ] Tests pass locally (`pytest`)
- [ ] Code is formatted and linted (`ruff`)
- [ ] Type checking passes (`mypy`)
- [ ] Documentation is updated
- [ ] Changelog entry added (if applicable)

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Tests added for new functionality
```

### Review Process

1. **Automated checks** must pass (CI/CD pipeline)
2. **Code review** by maintainers
3. **Testing** in development environment
4. **Approval** and merge by maintainers

## 🏷️ Release Process

### Versioning

We use [Semantic Versioning](https://semver.org/):
- `MAJOR.MINOR.PATCH` (e.g., `1.2.3`)
- `MAJOR`: Breaking changes
- `MINOR`: New features (backwards compatible)
- `PATCH`: Bug fixes (backwards compatible)

### Release Steps

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Create release PR
4. Tag release: `git tag v1.2.3`
5. Push tag: `git push origin v1.2.3`
6. GitHub Actions handles the rest

## 🤝 Community Guidelines

### Code of Conduct

- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on constructive feedback
- Assume good intentions

### Communication

- **GitHub Issues**: Bug reports, feature requests
- **GitHub Discussions**: General questions, ideas
- **Pull Requests**: Code changes, documentation updates

## 🆘 Getting Help

If you need help:

1. **Check the documentation** and existing issues
2. **Ask in GitHub Discussions** for general questions
3. **Create an issue** for bugs or specific problems
4. **Join our community** channels (if available)

## 🙏 Recognition

Contributors are recognized in:
- `CONTRIBUTORS.md` file
- Release notes
- GitHub contributor graphs
- Special mentions for significant contributions

Thank you for contributing to the Zulip Refinement Bot! 🎉
