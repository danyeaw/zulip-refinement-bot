"""
Zulip Refinement Bot

A modern Zulip bot for batch story point estimation and refinement workflows.
"""

__version__ = "1.0.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .bot import RefinementBot
from .config import Config
from .container import Container
from .database import DatabaseManager
from .database_pool import DatabasePool
from .github_api import GitHubAPI
from .handlers import MessageHandler
from .parser import InputParser
from .services import BatchService, ResultsService, VotingService

__all__ = [
    "RefinementBot",
    "Config",
    "Container",
    "DatabaseManager",
    "DatabasePool",
    "GitHubAPI",
    "InputParser",
    "BatchService",
    "VotingService",
    "ResultsService",
    "MessageHandler",
]
