"""
Zulip Refinement Bot

A modern Zulip bot for batch story point estimation and refinement workflows.
"""

__version__ = "1.0.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .bot import RefinementBot
from .config import Config

__all__ = ["RefinementBot", "Config"]
