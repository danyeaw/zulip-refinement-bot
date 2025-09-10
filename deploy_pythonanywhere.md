# Deploying Zulip Refinement Bot to PythonAnywhere

Quick deployment guide using PythonAnywhere's Flask support.

## Prerequisites

- A PythonAnywhere account
- Your Zulip bot credentials (email, API key, site URL, webhook token)

## Deployment

### 1. Create Flask Web App
1. Go to **Web** tab → **Add a new web app**
2. Choose **Flask** and **Python 3.13**
3. Use default path `/home/yourusername/mysite/`

### 2. Upload Bot Code
Replace the default Flask app with the bot:
```bash
cd ~/mysite
rm flask_app.py  # Remove default Flask app
git clone https://github.com/danyeaw/zulip-refinement-bot.git .
pip3.13 install --user -r requirements.txt
```

### 3. Configure Environment
```bash
cat > .env << 'EOF'
ZULIP_EMAIL=your-bot@yourdomain.zulipchat.com
ZULIP_API_KEY=your_api_key_here
ZULIP_SITE=https://yourdomain.zulipchat.com
ZULIP_TOKEN=your_webhook_token_here
STREAM_NAME=conda-maintainers
EOF
```

### 4. Setup Database
```bash
mkdir -p data
python3.13 -m zulip_refinement_bot.migrations.cli upgrade
```

### 5. Update WSGI File
Edit the auto-generated WSGI file to:
```python
import os
import sys

path = '/home/yourusername/mysite/src'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ.setdefault('DOTENV_PATH', '/home/yourusername/mysite/.env')

from zulip_refinement_bot.flask_app import app as application
```

### 6. Configure Zulip Webhook
In Zulip: **Organization** → **Bots** → Set webhook URL to: `https://yourusername.pythonanywhere.com/webhook`

### 7. Test
- **Reload** web app in Web tab
- Visit: `https://yourusername.pythonanywhere.com/health`
- Send bot a DM: `help`
