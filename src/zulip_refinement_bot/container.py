"""Dependency injection container for the Zulip Refinement Bot."""

from __future__ import annotations

from .config import Config
from .database_pool import DatabasePool
from .github_api import GitHubAPI
from .handlers import MessageHandler
from .interfaces import (
    DatabaseInterface,
    GitHubAPIInterface,
    MessageHandlerInterface,
    ParserInterface,
    ZulipClientInterface,
)
from .parser import InputParser
from .services import BatchService, ResultsService, VotingService
from .zulip_wrapper import ZulipClientWrapper


class Container:
    """Simple dependency injection container following BSSN principles."""

    def __init__(self, config: Config) -> None:
        """Initialize the container with configuration.

        Args:
            config: Bot configuration
        """
        self.config = config
        self._instances: dict[type, object] = {}

    def get_github_api(self) -> GitHubAPIInterface:
        """Get GitHub API instance.

        Returns:
            GitHub API interface implementation
        """
        if GitHubAPIInterface not in self._instances:
            self._instances[GitHubAPIInterface] = GitHubAPI(timeout=self.config.github_timeout)
        return self._instances[GitHubAPIInterface]  # type: ignore[return-value]

    def get_database(self) -> DatabaseInterface:
        """Get database manager instance.

        Returns:
            Database interface implementation
        """
        if DatabaseInterface not in self._instances:
            self._instances[DatabaseInterface] = DatabasePool(
                self.config.database_path, pool_size=5
            )
        return self._instances[DatabaseInterface]  # type: ignore[return-value]

    def get_parser(self) -> ParserInterface:
        """Get input parser instance.

        Returns:
            Parser interface implementation
        """
        if ParserInterface not in self._instances:
            # InputParser expects GitHubAPI, not GitHubAPIInterface
            github_api = self.get_github_api()
            if not isinstance(github_api, GitHubAPI):
                raise TypeError("Expected GitHubAPI instance")
            self._instances[ParserInterface] = InputParser(self.config, github_api)
        return self._instances[ParserInterface]  # type: ignore[return-value]

    def get_zulip_client(self) -> ZulipClientInterface:
        """Get Zulip client instance.

        Returns:
            Zulip client interface implementation
        """
        if ZulipClientInterface not in self._instances:
            self._instances[ZulipClientInterface] = ZulipClientWrapper(
                email=self.config.zulip_email,
                api_key=self.config.zulip_api_key,
                site=self.config.zulip_site,
            )
        return self._instances[ZulipClientInterface]  # type: ignore[return-value]

    def get_batch_service(self) -> BatchService:
        """Get batch service instance.

        Returns:
            Batch service implementation
        """
        if BatchService not in self._instances:
            self._instances[BatchService] = BatchService(
                config=self.config,
                database=self.get_database(),
                github_api=self.get_github_api(),
                parser=self.get_parser(),
            )
        return self._instances[BatchService]  # type: ignore[return-value]

    def get_voting_service(self) -> VotingService:
        """Get voting service instance.

        Returns:
            Voting service implementation
        """
        if VotingService not in self._instances:
            self._instances[VotingService] = VotingService(
                config=self.config,
                database=self.get_database(),
                parser=self.get_parser(),
            )
        return self._instances[VotingService]  # type: ignore[return-value]

    def get_results_service(self) -> ResultsService:
        """Get results service instance.

        Returns:
            Results service implementation
        """
        if ResultsService not in self._instances:
            self._instances[ResultsService] = ResultsService(config=self.config)
        return self._instances[ResultsService]  # type: ignore[return-value]

    def get_message_handler(self) -> MessageHandlerInterface:
        """Get message handler instance.

        Returns:
            Message handler interface implementation
        """
        if MessageHandlerInterface not in self._instances:
            self._instances[MessageHandlerInterface] = MessageHandler(
                config=self.config,
                zulip_client=self.get_zulip_client(),
                batch_service=self.get_batch_service(),
                voting_service=self.get_voting_service(),
                results_service=self.get_results_service(),
            )
        return self._instances[MessageHandlerInterface]  # type: ignore[return-value]

    def clear_cache(self) -> None:
        """Clear the instance cache (useful for testing).

        This allows fresh instances to be created on next access.
        """
        self._instances.clear()
