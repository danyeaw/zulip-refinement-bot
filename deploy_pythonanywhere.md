# Deploying Zulip Refinement Bot to PythonAnywhere

This guide explains how to deploy the Zulip Refinement Bot to PythonAnywhere.

## Prerequisites

1. A PythonAnywhere account (free tier works)
2. Your Zulip bot credentials (email, API key, site URL, webhook token)
3. Access to your Zulip organization's bot settings

## Deployment Steps

### 1. Upload Files to PythonAnywhere

1. Go to the **Files** tab in your PythonAnywhere dashboard
2. Create a new directory: `zulip-refinement-bot`
3. Upload all project files to this directory

### 2. Set Up Virtual Environment

Open a Bash console and run:

```bash
# Create virtual environment
mkvirtualenv zulip-bot --python=python3.13

# Navigate to your project directory
cd ~/zulip-refinement-bot

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in your project directory:

```bash
# Navigate to project directory
cd ~/zulip-refinement-bot

# Create environment file
cat > .env << 'EOF'
# Zulip connection settings
ZULIP_EMAIL=your-bot@yourdomain.zulipchat.com
ZULIP_API_KEY=your_api_key_here
ZULIP_SITE=https://yourdomain.zulipchat.com
ZULIP_TOKEN=your_webhook_token_here

# Bot configuration
STREAM_NAME=conda-maintainers
DEFAULT_DEADLINE_HOURS=48
MAX_ISSUES_PER_BATCH=6
MAX_TITLE_LENGTH=50

# Database settings
DATABASE_PATH=./data/refinement.db

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
EOF
```

**Important:** Replace the placeholders with your actual Zulip bot credentials. The webhook token can be found in your Zulip bot's outgoing webhook configuration and is required for security.

### 4. Set Up Database

```bash
# Create data directory
mkdir -p data

# Run database migrations
python -m zulip_refinement_bot.migrations.cli upgrade
```

### 5. Deploy as ASGI Application

Create an ASGI web application using the PythonAnywhere CLI:

```bash
# Install PythonAnywhere CLI tool
pip install --upgrade pythonanywhere

# Create ASGI website
pa website create --domain $USER.pythonanywhere.com --command "/home/$USER/.virtualenvs/zulip-bot/bin/uvicorn --app-dir /home/$USER/zulip-refinement-bot/src --uds \${DOMAIN_SOCKET} zulip_refinement_bot.fastapi_app:app"

If successful, you should see:
```
< All done! Your site is now live at $USER.pythonanywhere.com. >
   \
    ~<:>>>>>>>>>
```


### 6. Configure Zulip Outgoing Webhook

1. Go to your Zulip organization settings
2. Navigate to **Organization** > **Bots**
3. Find your bot and click **Edit**
4. Set the **Webhook URL** to: `https://$USER.pythonanywhere.com/webhook`
5. Save the configuration

### 6. Managing Your ASGI Website

Check your website status:
```bash
# List all websites
pa website get

# Get details for your specific website
pa website get --domain $USER.pythonanywhere.com

# Reload after code changes
pa website reload --domain $USER.pythonanywhere.com
```

### 7. Test the Deployment

1. **Test health endpoints:**
   - Visit: `https://$USER.pythonanywhere.com/health`
   - Visit: `https://$USER.pythonanywhere.com/`

2. **Check logs:**
   ```bash
   # View web app logs
   tail -f /var/log/$USER.pythonanywhere.com.error.log
   tail -f /var/log/$USER.pythonanywhere.com.access.log
   tail -f /var/log/$USER.pythonanywhere.com.server.log
   ```

3. **Send a direct message to your bot:** `help`

## Webhook URL Endpoints

Your deployed bot will respond to these endpoints:

- `GET /` - Health check
- `GET /health` - Health check
- `POST /webhook` - Main webhook endpoint for Zulip

## Troubleshooting

### Common Issues

1. **Import errors**: Make sure the `src` directory is in your Python path
2. **Database errors**: Ensure the `data` directory exists and is writable
3. **Configuration errors**: Check that all environment variables are set correctly
4. **ASGI issues**: If ASGI deployment fails, use the WSGI fallback method

### Debugging

1. Check PythonAnywhere error logs:
   ```bash
   tail -f /var/log/$USER.pythonanywhere.com.error.log
   ```

2. Test locally first:
   ```bash
   cd ~/zulip-refinement-bot
   python -c "from src.zulip_refinement_bot.fastapi_app import app; print('Import successful')"
   ```

3. Check environment variables:
   ```bash
   python -c "from src.zulip_refinement_bot.config import Config; print(Config())"
   ```

## Maintenance

### Updating the Bot

1. Upload new files to PythonAnywhere
2. Restart the web app from the **Web** tab
3. Run any necessary database migrations:
   ```bash
   cd ~/zulip-refinement-bot
   python -m zulip_refinement_bot.migrations.cli upgrade
   ```
