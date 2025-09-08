# Deploying Zulip Refinement Bot to PythonAnywhere

This guide explains how to deploy the FastAPI version of the Zulip Refinement Bot to PythonAnywhere.

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
mkvirtualenv zulip-bot --python=python3.11

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

PythonAnywhere supports ASGI applications in beta. Use the command-line tool:

```bash
# Install PythonAnywhere CLI tool
pip install --upgrade pythonanywhere

# Create ASGI web application
pa create_webapp --domain yourusername.pythonanywhere.com --python=3.11 --virtualenv=zulip-bot --command="/home/yourusername/.virtualenvs/zulip-bot/bin/uvicorn --app-dir /home/yourusername/zulip-refinement-bot/src --uds \${DOMAIN_SOCKET} zulip_refinement_bot.fastapi_app:app"
```

**Replace `yourusername` with your actual PythonAnywhere username.**

### 6. Alternative: Manual WSGI Setup

If ASGI deployment doesn't work, you can set up a traditional WSGI app:

1. Go to the **Web** tab in your PythonAnywhere dashboard
2. Click **Add a new web app**
3. Choose **Manual configuration** and **Python 3.11**
4. Edit the WSGI configuration file (`/var/www/yourusername_pythonanywhere_com_wsgi.py`):

```python
import os
import sys

# Add your project directory to the Python path
path = '/home/yourusername/zulip-refinement-bot'
if path not in sys.path:
    sys.path.append(path)

# Add the src directory to the Python path
src_path = '/home/yourusername/zulip-refinement-bot/src'
if src_path not in sys.path:
    sys.path.append(src_path)

# Set environment variables
os.environ['PYTHONPATH'] = src_path

# Import the FastAPI application
from zulip_refinement_bot.fastapi_app import app

# For ASGI apps, use uvicorn WSGI adapter
from uvicorn.middleware.wsgi import WSGIMiddleware
application = WSGIMiddleware(app)
```

5. Set the **Virtualenv** to `/home/yourusername/.virtualenvs/zulip-bot`
6. Reload the web app

### 7. Configure Zulip Outgoing Webhook

1. Go to your Zulip organization settings
2. Navigate to **Organization** > **Bots**
3. Find your bot and click **Edit**
4. Set the **Webhook URL** to: `https://yourusername.pythonanywhere.com/webhook`
5. Save the configuration

### 8. Test the Deployment

1. Send a direct message to your bot: `help`
2. Check the PythonAnywhere logs:
   ```bash
   # View web app logs
   tail -f /var/log/yourusername.pythonanywhere.com.error.log
   tail -f /var/log/yourusername.pythonanywhere.com.access.log
   ```

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
   tail -f /var/log/yourusername.pythonanywhere.com.error.log
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

### Monitoring

- Check logs regularly for errors
- Monitor the health endpoint: `https://yourusername.pythonanywhere.com/health`
- Test bot functionality periodically

## Security Notes

1. Keep your `.env` file secure and never commit it to version control
2. Regularly rotate your Zulip API keys
3. Monitor access logs for unusual activity
4. Keep dependencies updated

## Support

- PythonAnywhere ASGI documentation: https://help.pythonanywhere.com/pages/ASGICommandLine
- Zulip bot documentation: https://zulip.com/api/bots-guide
- FastAPI deployment guide: https://fastapi.tiangolo.com/deployment/
