# Zulip Refinement Bot

[![CI](https://github.com/yourusername/zulip-refinement-bot/workflows/CI/badge.svg)](https://github.com/yourusername/zulip-refinement-bot/actions)
[![codecov](https://codecov.io/gh/yourusername/zulip-refinement-bot/branch/main/graph/badge.svg)](https://codecov.io/gh/yourusername/zulip-refinement-bot)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A modern, production-ready Zulip bot for batch story point estimation and refinement workflows. Built with Python 3.11+, conda for dependency management, and designed for easy deployment to production environments.

## ✨ Features

- **🔗 GitHub Integration**: Automatically fetch issue titles from GitHub URLs
- **📦 Batch Management**: Create estimation batches with multiple GitHub issues
- **✅ Input Validation**: Strict URL format checking and duplicate prevention
- **🎯 Topic Management**: Automated topic creation in Zulip streams
- **📊 Status Tracking**: Check active batch status and progress
- **🚫 Cancellation**: Facilitators can cancel active batches
- **🐳 Docker Ready**: Production-ready containerization
- **🧪 Fully Tested**: Comprehensive test suite with high coverage
- **📝 Type Safe**: Full type hints and mypy validation
- **🔧 Modern Tooling**: Ruff for formatting and linting, mypy for type checking, and pre-commit hooks

## 🚀 Quick Start

### Using Conda (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/zulip-refinement-bot.git
cd zulip-refinement-bot

# Create and activate conda environment
conda env create -f environment.yml
conda activate zulip-refinement-bot

# Install the package
pip install -e .

# Generate configuration template
zulip-refinement-bot init-config

# Edit .env with your Zulip credentials
# Then run the bot
zulip-refinement-bot run
```

### Using Docker

```bash
# Clone the repository
git clone https://github.com/yourusername/zulip-refinement-bot.git
cd zulip-refinement-bot

# Copy and edit environment file
cp .env.example .env
# Edit .env with your Zulip credentials

# Run with Docker Compose
docker-compose up -d
```

### Using pip

```bash
# Install from PyPI (when available)
pip install zulip-refinement-bot

# Generate configuration
zulip-refinement-bot init-config

# Edit .env and run
zulip-refinement-bot run
```

## 📋 Configuration

The bot uses environment variables for configuration. Generate a template with:

```bash
zulip-refinement-bot init-config
```

### Required Settings

```env
# Zulip connection (required)
ZULIP_EMAIL=your-bot@yourdomain.zulipchat.com
ZULIP_API_KEY=your_api_key_here
ZULIP_SITE=https://yourdomain.zulipchat.com
```

### Optional Settings

```env
# Bot configuration
STREAM_NAME=conda-maintainers
DEFAULT_DEADLINE_HOURS=48
MAX_ISSUES_PER_BATCH=6
MAX_TITLE_LENGTH=50

# Voter list (comma-separated)
VOTER_LIST=voter1,voter2,voter3

# Database and logging
DATABASE_PATH=./data/refinement.db
LOG_LEVEL=INFO
LOG_FORMAT=console
```

## 💬 Usage

### Commands (DM only)

- **`start batch`** - Create new estimation batch
- **`status`** - Show active batch info
- **`cancel`** - Cancel active batch (facilitator only)
- **`help`** - Show usage instructions

### Creating a Batch

Send a DM to the bot with GitHub issue URLs:

```
start batch
https://github.com/conda/conda/issues/15169
https://github.com/conda/conda/issues/15168
https://github.com/conda/conda/issues/15167
```

The bot will:
1. ✅ Validate all URLs and fetch issue titles
2. 📝 Create a batch in the database
3. 💬 Send you a confirmation message
4. 🎯 Create a topic in the configured stream
5. 👥 Mention all voters for estimation

### Rules and Limits

- 🔗 **GitHub URLs only** - No manual title entry needed
- 📊 **Maximum 6 issues per batch** (configurable)
- 🔄 **Only one active batch at a time**
- ✂️ **Issue titles automatically truncated at 50 characters**
- ⏰ **48-hour default deadline** (configurable)
- 🔒 **Commands work via DM only**

## 🏗️ Architecture

```
src/zulip_refinement_bot/
├── __init__.py          # Package initialization
├── bot.py              # Main bot implementation
├── cli.py              # Command-line interface
├── config.py           # Configuration management
├── database.py         # SQLite database operations
├── github_api.py       # GitHub API integration
├── models.py           # Pydantic data models
└── parser.py           # Input parsing and validation
```

## 🧪 Development

### Setup Development Environment

```bash
# Clone and setup
git clone https://github.com/yourusername/zulip-refinement-bot.git
cd zulip-refinement-bot
conda env create -f environment.yml
conda activate zulip-refinement-bot
pip install -e ".[dev,test]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/zulip_refinement_bot --cov-report=html

# Run specific test file
pytest tests/test_bot.py -v

# Run with different markers
pytest -m "not slow"  # Skip slow tests
pytest -m integration  # Only integration tests
```

### Code Quality

```bash
# Format and lint code
ruff format src/ tests/
ruff check src/ tests/
mypy src/

# Run all quality checks
pre-commit run --all-files
```

## 🐳 Production Deployment

### Docker Compose (Recommended)

```bash
# Production deployment
docker-compose -f docker-compose.yml up -d

# With monitoring
docker-compose --profile monitoring up -d

# View logs
docker-compose logs -f zulip-refinement-bot
```

### Kubernetes

```yaml
# Example Kubernetes deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: zulip-refinement-bot
spec:
  replicas: 1
  selector:
    matchLabels:
      app: zulip-refinement-bot
  template:
    metadata:
      labels:
        app: zulip-refinement-bot
    spec:
      containers:
      - name: bot
        image: ghcr.io/yourusername/zulip-refinement-bot:latest
        env:
        - name: ZULIP_EMAIL
          valueFrom:
            secretKeyRef:
              name: zulip-secrets
              key: email
        - name: ZULIP_API_KEY
          valueFrom:
            secretKeyRef:
              name: zulip-secrets
              key: api-key
        - name: ZULIP_SITE
          valueFrom:
            secretKeyRef:
              name: zulip-secrets
              key: site
        volumeMounts:
        - name: data
          mountPath: /app/data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: bot-data
```

### Environment Variables for Production

```env
# Production settings
LOG_FORMAT=json
LOG_LEVEL=INFO
DATABASE_PATH=/app/data/refinement.db

# Resource limits in docker-compose.yml
# CPU: 0.5 cores, Memory: 512MB
```

## 📊 Monitoring

### Health Checks

The bot includes health check endpoints:

```bash
# Docker health check
docker-compose ps

# Manual health check
conda run -n zulip-refinement-bot python -c "import sys; sys.exit(0)"
```

### Logging

Structured logging with configurable formats:

```bash
# Console logging (development)
zulip-refinement-bot run --log-format console

# JSON logging (production)
zulip-refinement-bot run --log-format json
```

### Metrics

Monitor these key metrics:
- 📊 **Batch creation rate**
- ⏱️ **GitHub API response times**
- 🗄️ **Database operation latency**
- 💾 **Memory usage**
- 🔄 **Message processing rate**

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Workflow

1. 🍴 Fork the repository
2. 🌿 Create a feature branch
3. ✅ Make changes with tests
4. 🧪 Run the test suite
5. 📝 Update documentation
6. 🔄 Submit a pull request

### Code Standards

- ✅ **100% test coverage** for new features
- 📝 **Type hints** for all functions
- 📚 **Docstrings** for public APIs
- 🎨 **Ruff** code formatting and linting
- 🔍 **mypy** type checking compliance
- 🏷️ **Conventional commits**

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built for the [conda](https://github.com/conda/conda) team's refinement workflow
- Powered by [Zulip](https://zulip.com/) for team communication
- Uses [GitHub API](https://docs.github.com/en/rest) for issue integration

## 📞 Support

- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/yourusername/zulip-refinement-bot/issues)
- 💡 **Feature Requests**: [GitHub Discussions](https://github.com/yourusername/zulip-refinement-bot/discussions)
- 📧 **Email**: your.email@example.com

---

<div align="center">

**[Documentation](https://github.com/yourusername/zulip-refinement-bot#readme)** •
**[Installation](https://github.com/yourusername/zulip-refinement-bot#-quick-start)** •
**[Configuration](https://github.com/yourusername/zulip-refinement-bot#-configuration)** •
**[Contributing](CONTRIBUTING.md)**

Made with ❤️ for agile teams

</div>
