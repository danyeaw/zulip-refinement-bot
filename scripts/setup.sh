#!/bin/bash
# Setup script for Zulip Refinement Bot development environment

set -e

echo "🚀 Setting up Zulip Refinement Bot development environment..."

# Check if conda is available
if ! command -v conda &> /dev/null; then
    echo "❌ Conda not found. Please install Miniconda or Anaconda first."
    echo "   Download from: https://docs.conda.io/en/latest/miniconda.html"
    exit 1
fi

# Create conda environment
echo "📦 Creating conda environment..."
conda env create -f environment.yml

# Activate environment and install package
echo "🔧 Installing package in development mode..."
eval "$(conda shell.bash hook)"
conda activate zulip-refinement-bot
pip install -e ".[dev,test]"

# Install pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
pre-commit install

# Create data directory
echo "📁 Creating data directory..."
mkdir -p data

# Generate configuration template
echo "⚙️  Generating configuration template..."
zulip-refinement-bot init-config --output env.example --force

# Run tests to verify setup
echo "🧪 Running tests to verify setup..."
pytest --tb=short

echo ""
echo "✅ Setup complete! Next steps:"
echo ""
echo "1. Activate the environment:"
echo "   conda activate zulip-refinement-bot"
echo ""
echo "2. Copy and edit configuration:"
echo "   cp env.example .env"
echo "   # Edit .env with your Zulip credentials"
echo ""
echo "3. Run the bot:"
echo "   zulip-refinement-bot run"
echo ""
echo "4. Or run in development mode:"
echo "   zulip-refinement-bot run --log-format console"
echo ""
echo "📚 See README.md for more information!"
