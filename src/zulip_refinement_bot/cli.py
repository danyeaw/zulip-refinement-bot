"""Command-line interface for the Zulip Refinement Bot."""

from __future__ import annotations

import sys
from pathlib import Path

import structlog
import typer
from rich.console import Console
from rich.logging import RichHandler

from . import __version__
from .bot import RefinementBot
from .config import Config
from .migrations.cli import app as migrate_app

app = typer.Typer(
    name="zulip-refinement-bot",
    help="A modern Zulip bot for batch story point estimation and refinement workflows.",
    add_completion=False,
)

# Add migration commands as a subcommand
app.add_typer(migrate_app, name="migrate")
console = Console()


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Set up structured logging.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_format: Log format (json, console)
    """
    import logging

    level = getattr(logging, log_level.upper(), logging.INFO)

    if log_format.lower() == "console":
        # Rich console logging for development
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        # Configure standard library logging
        logging.basicConfig(
            format="%(message)s",
            level=level,
            handlers=[RichHandler(console=console, rich_tracebacks=True)],
        )
    else:
        # JSON logging for production
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )


@app.command()  # type: ignore[misc]
def run(
    config_file: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file (.env format)",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        "-l",
        help="Logging level",
        case_sensitive=False,
    ),
    log_format: str = typer.Option(
        "console",
        "--log-format",
        "-f",
        help="Log format (console or json)",
        case_sensitive=False,
    ),
) -> None:
    """Run the Zulip Refinement Bot."""

    # Set up logging first
    setup_logging(log_level, log_format)
    logger = structlog.get_logger(__name__)

    try:
        # Load configuration
        if config_file:
            config = Config(_env_file=config_file)
        else:
            config = Config()

        # Override log settings from CLI
        config.log_level = log_level.upper()
        config.log_format = log_format.lower()

        logger.info("Starting Zulip Refinement Bot", version=__version__)

        # Create and run bot
        bot = RefinementBot(config)
        bot.run()

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        console.print("\n👋 Bot stopped gracefully")
        sys.exit(0)
    except Exception as e:
        logger.error("Failed to start bot", error=str(e))
        console.print(f"❌ [red]Error:[/red] {e}")
        sys.exit(1)


@app.command()  # type: ignore[misc]
def version() -> None:
    """Show version information."""
    console.print(f"Zulip Refinement Bot v{__version__}")


@app.command()  # type: ignore[misc]
def server(
    host: str = typer.Option(
        "127.0.0.1",  # nosec B104 - Default to localhost for security, can be overridden
        "--host",
        "-h",
        help="Host to bind the server to (use 0.0.0.0 for external access)",
    ),
    port: int = typer.Option(
        8000,
        "--port",
        "-p",
        help="Port to bind the server to",
    ),
    reload: bool = typer.Option(
        False,
        "--reload",
        "-r",
        help="Enable auto-reload for development",
    ),
    config_file: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file (.env format)",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        "-l",
        help="Logging level",
        case_sensitive=False,
    ),
    log_format: str = typer.Option(
        "console",
        "--log-format",
        "-f",
        help="Log format (console or json)",
        case_sensitive=False,
    ),
) -> None:
    """Run the FastAPI webhook server for the Zulip Refinement Bot."""
    import uvicorn

    # Set up logging first
    setup_logging(log_level, log_format)
    logger = structlog.get_logger(__name__)

    try:
        # Load configuration to validate it
        from .config import Config

        if config_file:
            Config(_env_file=config_file)
        else:
            Config()

        logger.info(
            "Starting FastAPI server for Zulip Refinement Bot",
            host=host,
            port=port,
            reload=reload,
        )

        # Run the FastAPI server
        uvicorn.run(
            "zulip_refinement_bot.fastapi_app:app",
            host=host,
            port=port,
            reload=reload,
            log_level=log_level.lower(),
        )

    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        console.print("\n👋 Server stopped gracefully")
        sys.exit(0)
    except Exception as e:
        logger.error("Failed to start server", error=str(e))
        console.print(f"❌ [red]Error:[/red] {e}")
        sys.exit(1)


@app.command()  # type: ignore[misc]
def init_config(
    output: Path = typer.Option(
        Path(".env"),
        "--output",
        "-o",
        help="Output file path for configuration template",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing configuration file",
    ),
) -> None:
    """Generate a configuration file template."""

    if output.exists() and not force:
        console.print(f"❌ Configuration file {output} already exists. Use --force to overwrite.")
        sys.exit(1)

    config_template = """# Zulip Refinement Bot Configuration
# Copy this file to .env and fill in your values

# Zulip connection settings (required)
ZULIP_EMAIL=your-bot@yourdomain.zulipchat.com
ZULIP_API_KEY=your_api_key_here
ZULIP_SITE=https://yourdomain.zulipchat.com

# Bot configuration (optional)
STREAM_NAME=conda-maintainers
DEFAULT_DEADLINE_HOURS=48
MAX_ISSUES_PER_BATCH=6
MAX_TITLE_LENGTH=50

# Database settings (optional)
DATABASE_PATH=./data/refinement.db

# GitHub API settings (optional)
GITHUB_TIMEOUT=10.0

# Logging (optional)
LOG_LEVEL=INFO
LOG_FORMAT=console
"""

    try:
        output.write_text(config_template)
        console.print(f"✅ Configuration template written to {output}")
        console.print("📝 Edit the file and add your Zulip credentials to get started")
    except Exception as e:
        console.print(f"❌ [red]Error writing config file:[/red] {e}")
        sys.exit(1)


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
