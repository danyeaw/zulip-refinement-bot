# Zulip Refinement Bot

[![CI](https://github.com/danyeaw/zulip-refinement-bot/workflows/CI/badge.svg)](https://github.com/danyeaw/zulip-refinement-bot/actions)
[![codecov](https://codecov.io/gh/danyeaw/zulip-refinement-bot/branch/main/graph/badge.svg)](https://codecov.io/gh/danyeaw/zulip-refinement-bot)

A Zulip bot for team story point estimation sessions. Fetches GitHub issues, manages voting, and builds consensus through discussion when needed.

## Quick Start

```bash
git clone https://github.com/danyeaw/zulip-refinement-bot.git
cd zulip-refinement-bot

# Install dependencies
conda env create -f environment.yml && conda activate zulip-refinement-bot
# OR: pip install -r requirements.txt

pip install -e .

# Configure
zulip-refinement-bot init-config
# Edit .env with your Zulip bot credentials

# Run
zulip-refinement-bot server
```

## Configuration

Required `.env` settings:
```env
ZULIP_EMAIL=your-bot@yourdomain.zulipchat.com
ZULIP_API_KEY=your_api_key_here
ZULIP_SITE=https://yourdomain.zulipchat.com
ZULIP_TOKEN=your_webhook_token_here
```

## Usage

### Start a Session
DM the bot with GitHub issue URLs:
```
start batch
https://github.com/conda/conda/issues/15169
https://github.com/conda/conda/issues/15168
```

### Vote
DM your estimates using Fibonacci points (1, 2, 3, 5, 8, 13, 21):
```
#15169: 5, #15168: 8
```

### Proxy Voting (Facilitator Only)
The facilitator can submit votes on behalf of other users:
```
vote for @**username** #15169: 5, #15168: 8
vote for John Doe #15169: 5, #15168: 8
```

### Manage Voters
```
list
add Alice, Bob
remove John
```

### Complete Discussion
When consensus isn't reached, the facilitator can finalize individual items or multiple items:
```
finish #15169: 5 After discussion we agreed it's medium complexity
finish #15168: 3 Simple fix, #15167: 8 More complex than expected
```
The system automatically updates results as items are completed and finishes the batch when all discussion items are done.

## Commands

- `start` - Create new estimation session
- `status` - Show current session status
- `complete` - Complete active batch and show results (facilitator only)
- `cancel` - Cancel session (facilitator only)
- `finish #issue: points rationale` - Complete individual discussion items (facilitator only)

## Development

```bash
pip install -e ".[dev,test]"
pytest                           # Run tests
pre-commit run --all-files      # Code quality checks
```

## License

MIT License - see [LICENSE](LICENSE) file for details.
