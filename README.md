# Zulip Refinement Bot

[![CI](https://github.com/danyeaw/zulip-refinement-bot/workflows/CI/badge.svg)](https://github.com/danyeaw/zulip-refinement-bot/actions)
[![codecov](https://codecov.io/gh/danyeaw/zulip-refinement-bot/branch/main/graph/badge.svg)](https://codecov.io/gh/danyeaw/zulip-refinement-bot)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A Zulip bot for batch story point estimation workflows. Fetches GitHub issues, manages voting sessions, and generates consensus reports.

## Features

- GitHub integration for automatic issue title fetching
- Batch estimation sessions with configurable deadlines
- Fibonacci story point validation (1, 2, 3, 5, 8, 13, 21)
- Automated consensus analysis and reporting
- **Discussion phase** - automatically triggered when consensus isn't reached
- **Multi-voter support** - add/remove multiple voters in single commands
- Docker deployment support
- Full type safety and comprehensive testing

## Quick Start

### Using Conda

```bash
git clone https://github.com/danyeaw/zulip-refinement-bot.git
cd zulip-refinement-bot

conda env create -f environment.yml
conda activate zulip-refinement-bot
pip install -e .

zulip-refinement-bot init-config
# Edit .env with your Zulip credentials
zulip-refinement-bot run
```

### Using Docker

```bash
git clone https://github.com/danyeaw/zulip-refinement-bot.git
cd zulip-refinement-bot

cp .env.example .env
# Edit .env with your Zulip credentials
docker-compose up -d
```

## Configuration

Generate a configuration template:

```bash
zulip-refinement-bot init-config
```

Required settings:

```env
ZULIP_EMAIL=your-bot@yourdomain.zulipchat.com
ZULIP_API_KEY=your_api_key_here
ZULIP_SITE=https://yourdomain.zulipchat.com
```

Optional settings:

```env
STREAM_NAME=conda-maintainers
DEFAULT_DEADLINE_HOURS=48
MAX_ISSUES_PER_BATCH=6
DATABASE_PATH=./data/refinement.db
```

## Usage

### Commands (DM only)

- `start batch` - Create new estimation batch
- `status` - Show active batch info
- `cancel` - Cancel active batch (facilitator only)
- `complete` - Complete active batch (facilitator only)
- `discussion complete #issue: points rationale` - Complete discussion phase (facilitator only)
- `list voters` - Show voters for active batch
- `add voter Name` - Add voter(s) to active batch (supports multiple)
- `remove voter Name` - Remove voter(s) from active batch (supports multiple)

### Creating a Batch

Send a DM to the bot with GitHub issue URLs:

```
start batch
https://github.com/conda/conda/issues/15169
https://github.com/conda/conda/issues/15168
https://github.com/conda/conda/issues/15167
```

### Voting

Vote by DMing the bot with story points for each issue:

```
#15169: 5, #15168: 8, #15167: 3
```

Valid story points: 1, 2, 3, 5, 8, 13, 21 (Fibonacci sequence)

### Voter Management

Each batch has its own voter list. You can add/remove voters individually or in groups:

```
list voters                           # See who's voting on current batch
add voter Jane Doe                    # Add single person
add voter Alice, Bob, @**charlie**    # Add multiple people
remove voter John Smith               # Remove single person
remove voter Alice and Bob            # Remove multiple people
```

New voters are automatically added if they submit votes but aren't on the list.

### Discussion Phase

When voting completes, the bot analyzes results:

- **Consensus reached**: Issues with clear agreement are finalized automatically
- **Discussion needed**: Issues with wide spread or mixed clusters trigger discussion phase

During discussion phase:
1. Team discusses disputed estimates in the stream
2. Facilitator finalizes estimates using: `discussion complete #15169: 5 After discussion we agreed it's medium complexity`
3. Bot posts final results with rationale

### Rules

- Maximum 6 issues per batch
- Only one active batch at a time
- 48-hour default deadline
- All voters must vote on all issues
- Discussion phase automatically triggered when consensus isn't reached

## Architecture

```
src/zulip_refinement_bot/
├── bot.py              # Main bot implementation
├── services.py         # Business logic (batch, voting, results)
├── handlers.py         # Message routing and formatting
├── database_pool.py    # Database with connection pooling
├── github_api.py       # GitHub API integration
├── parser.py           # Input parsing and validation
├── config.py           # Configuration management
├── models.py           # Data models
├── interfaces.py       # Abstract interfaces
├── container.py        # Dependency injection
└── exceptions.py       # Custom exceptions
```

## Development

### Setup

```bash
git clone https://github.com/danyeaw/zulip-refinement-bot.git
cd zulip-refinement-bot
conda env create -f environment.yml
conda activate zulip-refinement-bot
pip install -e ".[dev,test]"
pre-commit install
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=src/zulip_refinement_bot --cov-report=html

# Run specific test categories
pytest tests/test_multi_voter.py          # Multi-voter functionality
pytest tests/test_discussion_complete.py  # Discussion complete feature
pytest tests/test_voting_service.py       # Voting logic
```

### Code Quality

```bash
ruff format src/ tests/
ruff check src/ tests/
mypy src/
```

## Deployment

### Docker Compose

```bash
docker-compose up -d
docker-compose logs -f zulip-refinement-bot
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run the test suite
5. Submit a pull request

Built for the conda team's refinement workflow.
