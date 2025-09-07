"""Service layer for business logic operations."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

import structlog

from .business_hours import BusinessHoursCalculator
from .config import Config
from .exceptions import AuthorizationError, BatchError, ValidationError, VotingError
from .interfaces import DatabaseInterface, GitHubAPIInterface, ParserInterface
from .models import BatchData, EstimationVote, FinalEstimate, IssueData

logger = structlog.get_logger(__name__)


class BatchService:
    """Service for managing batch operations."""

    def __init__(
        self,
        config: Config,
        database: DatabaseInterface,
        github_api: GitHubAPIInterface,
        parser: ParserInterface,
    ) -> None:
        self.config = config
        self.database = database
        self.github_api = github_api
        self.parser = parser
        self.business_hours_calc = BusinessHoursCalculator(config)

    def create_batch(self, content: str, facilitator: str) -> tuple[int, list[IssueData], datetime]:
        """Create a new batch from input content."""
        active_batch = self.database.get_active_batch()
        if active_batch:
            raise BatchError("Active batch already running. Use 'status' to check progress.")

        parse_result = self.parser.parse_batch_input(content)
        if not parse_result.success:
            raise ValidationError(parse_result.error)
        now = datetime.now(UTC)
        date_str = now.strftime("%Y-%m-%d")

        # Calculate deadline using business hours if enabled
        deadline = self.business_hours_calc.add_business_hours(
            now, self.config.default_deadline_hours
        )
        deadline_str = deadline.isoformat()

        try:
            batch_id = self.database.create_batch(date_str, deadline_str, facilitator)
            self.database.add_issues_to_batch(batch_id, parse_result.issues)
            from .config import Config

            self.database.add_batch_voters(batch_id, Config._default_voters)

            logger.info(
                "Batch created successfully",
                batch_id=batch_id,
                facilitator=facilitator,
                issue_count=len(parse_result.issues),
                voter_count=len(Config._default_voters),
            )

            return batch_id, parse_result.issues, deadline

        except Exception as e:
            logger.error("Error creating batch", error=str(e))
            raise BatchError(f"Error creating batch: {str(e)}") from e

    def get_active_batch(self) -> BatchData | None:
        """Get the currently active batch.

        Returns:
            Active batch data or None if no active batch exists
        """
        return self.database.get_active_batch()

    def cancel_batch(self, batch_id: int, requester: str) -> None:
        """Cancel an active batch.

        Args:
            batch_id: ID of the batch to cancel
            requester: Name of the person requesting cancellation

        Raises:
            BatchError: If no active batch exists
            AuthorizationError: If requester is not the facilitator
        """
        active_batch = self.database.get_active_batch()
        if not active_batch:
            raise BatchError("No active batch to cancel.")

        if requester != active_batch.facilitator:
            raise AuthorizationError(
                f"Only the facilitator ({active_batch.facilitator}) can cancel this batch."
            )

        if active_batch.id != batch_id:
            raise BatchError("Batch ID mismatch.")

        self.database.cancel_batch(batch_id)
        logger.info("Batch cancelled", batch_id=batch_id, requester=requester)

    def complete_batch(self, batch_id: int, requester: str) -> BatchData:
        """Complete an active batch.

        Args:
            batch_id: ID of the batch to complete
            requester: Name of the person requesting completion

        Returns:
            The completed batch data

        Raises:
            BatchError: If no active batch exists
            AuthorizationError: If requester is not the facilitator
        """
        active_batch = self.database.get_active_batch()
        if not active_batch:
            raise BatchError("No active batch to complete.")

        if requester != active_batch.facilitator:
            raise AuthorizationError(
                f"Only the facilitator ({active_batch.facilitator}) can complete this batch."
            )

        if active_batch.id != batch_id:
            raise BatchError("Batch ID mismatch.")

        self.database.complete_batch(batch_id)
        logger.info("Batch completed", batch_id=batch_id, requester=requester)

        return active_batch

    def start_discussion_phase(self, batch_id: int, requester: str) -> BatchData:
        """Start the discussion phase for a batch.

        Args:
            batch_id: ID of the batch to move to discussion phase
            requester: Name of the person requesting the transition

        Returns:
            The updated batch data

        Raises:
            BatchError: If no active batch exists or batch is not in correct state
            AuthorizationError: If requester is not the facilitator
        """
        active_batch = self.database.get_active_batch()
        if not active_batch:
            raise BatchError("No active batch found.")

        if requester != active_batch.facilitator:
            raise AuthorizationError(
                f"Only the facilitator ({active_batch.facilitator}) can start discussion phase."
            )

        if active_batch.id != batch_id:
            raise BatchError("Batch ID mismatch.")

        if active_batch.status != "active":
            raise BatchError(f"Batch is not in active state (current: {active_batch.status}).")

        self.database.set_batch_discussing(batch_id)
        logger.info("Batch moved to discussion phase", batch_id=batch_id, requester=requester)

        # Update the batch status locally
        active_batch.status = "discussing"
        return active_batch

    def complete_discussion_phase(
        self, batch_id: int, requester: str, final_estimates: dict[str, tuple[int, str]]
    ) -> BatchData:
        """Complete the discussion phase with final estimates.

        Args:
            batch_id: ID of the batch to complete discussion for
            requester: Name of the person requesting completion
            final_estimates: Dict of issue_number -> (final_points, rationale)

        Returns:
            The completed batch data

        Raises:
            BatchError: If no discussing batch exists
            AuthorizationError: If requester is not the facilitator
        """
        active_batch = self.database.get_active_batch()
        if not active_batch:
            raise BatchError("No active batch found.")

        if requester != active_batch.facilitator:
            raise AuthorizationError(
                f"Only the facilitator ({active_batch.facilitator}) can complete discussion phase."
            )

        if active_batch.id != batch_id:
            raise BatchError("Batch ID mismatch.")

        if active_batch.status != "discussing":
            raise BatchError(f"Batch is not in discussion phase (current: {active_batch.status}).")

        # Store final estimates
        for issue_number, (final_points, rationale) in final_estimates.items():
            self.database.store_final_estimate(batch_id, issue_number, final_points, rationale)

        # Complete the batch
        self.database.complete_batch(batch_id)
        logger.info(
            "Discussion phase completed",
            batch_id=batch_id,
            requester=requester,
            final_estimates_count=len(final_estimates),
        )

        # Update the batch status locally
        active_batch.status = "completed"
        return active_batch


class VotingService:
    """Service for managing voting operations."""

    def __init__(
        self,
        config: Config,
        database: DatabaseInterface,
        parser: ParserInterface,
    ) -> None:
        """Initialize voting service.

        Args:
            config: Bot configuration
            database: Database interface
            parser: Parser interface
        """
        self.config = config
        self.database = database
        self.parser = parser

    def submit_votes(
        self, content: str, voter: str, batch: BatchData
    ) -> tuple[dict[str, int], bool, bool]:
        """Submit votes for a batch.

        Args:
            content: Vote content
            voter: Name of the voter
            batch: Active batch data

        Returns:
            Tuple of (estimates, has_updates, all_voters_complete)

        Raises:
            AuthorizationError: If voter is not authorized
            ValidationError: If vote validation fails
            VotingError: If vote storage fails
        """
        if batch.id is None:
            raise VotingError("No active batch found. Cannot submit votes.")

        batch_voters = self.database.get_batch_voters(batch.id)
        if voter not in batch_voters:
            was_added = self.database.add_voter_to_batch(batch.id, voter)
            if was_added:
                logger.info("Added new voter to batch", batch_id=batch.id, voter=voter)

        estimates, validation_errors = self.parser.parse_estimation_input(content)

        if validation_errors:
            error_msg = "Invalid story point values found:\n"
            for error in validation_errors:
                error_msg += f"  • {error}\n"
            error_msg += "\nValid story points (Fibonacci sequence): 1, 2, 3, 5, 8, 13, 21"
            raise ValidationError(error_msg)

        if not estimates:
            raise ValidationError(
                "No valid votes found. Please use format: `#1234: 5, #1235: 8, #1236: 3`\n"
                "Valid story points: 1, 2, 3, 5, 8, 13, 21"
            )

        self._validate_vote_completeness(estimates, batch)

        stored_count, updated_count, new_count = self._store_votes(batch.id, voter, estimates)

        if stored_count != len(estimates):
            raise VotingError(
                f"Only {stored_count} out of {len(estimates)} votes were processed successfully."
            )

        vote_count = self.database.get_vote_count_by_voter(batch.id)
        batch_voters = self.database.get_batch_voters(batch.id)
        all_voters_complete = vote_count >= len(batch_voters)

        logger.info(
            "Votes submitted successfully",
            batch_id=batch.id,
            voter=voter,
            new_votes=new_count,
            updated_votes=updated_count,
            all_voters_complete=all_voters_complete,
        )

        return estimates, stored_count > 0, all_voters_complete

    def _validate_vote_completeness(self, estimates: dict[str, int], batch: BatchData) -> None:
        """Validate that all batch issues are voted on.

        Args:
            estimates: Vote estimates
            batch: Batch data

        Raises:
            ValidationError: If vote validation fails
        """
        batch_issue_numbers = {issue.issue_number for issue in batch.issues}
        voted_issue_numbers = set(estimates.keys())

        missing_votes = batch_issue_numbers - voted_issue_numbers
        extra_votes = voted_issue_numbers - batch_issue_numbers

        if missing_votes or extra_votes:
            error_msg = "Vote validation failed:\n"
            if missing_votes:
                missing_list = ", ".join(f"#{num}" for num in missing_votes)
                error_msg += f"Missing votes for issues: {missing_list}\n"
            if extra_votes:
                extra_list = ", ".join(f"#{num}" for num in extra_votes)
                error_msg += f"Votes for issues not in batch: {extra_list}\n"

            required_list = ", ".join(f"#{num}" for num in batch_issue_numbers)
            error_msg += f"\nPlease vote for exactly these issues: {required_list}"
            raise ValidationError(error_msg)

    def _store_votes(
        self, batch_id: int, voter: str, estimates: dict[str, int]
    ) -> tuple[int, int, int]:
        """Store votes in the database.

        Args:
            batch_id: Batch ID
            voter: Voter name
            estimates: Vote estimates

        Returns:
            Tuple of (stored_count, updated_count, new_count)
        """
        stored_count = 0
        updated_count = 0
        new_count = 0

        for issue_number, points in estimates.items():
            success, was_update = self.database.upsert_vote(batch_id, voter, issue_number, points)
            if success:
                stored_count += 1
                if was_update:
                    updated_count += 1
                else:
                    new_count += 1

        return stored_count, updated_count, new_count

    def get_batch_votes(self, batch_id: int) -> list[EstimationVote]:
        """Get all votes for a batch.

        Args:
            batch_id: Batch ID

        Returns:
            List of votes for the batch
        """
        return self.database.get_batch_votes(batch_id)

    def check_completion_status(self, batch_id: int) -> tuple[int, int, bool]:
        """Check if all voters have completed voting.

        Args:
            batch_id: Batch ID

        Returns:
            Tuple of (vote_count, total_voters, is_complete)
        """
        vote_count = self.database.get_vote_count_by_voter(batch_id)
        batch_voters = self.database.get_batch_voters(batch_id)
        total_voters = len(batch_voters)
        is_complete = vote_count >= total_voters

        return vote_count, total_voters, is_complete


class ResultsService:
    """Service for generating and analyzing estimation results."""

    def __init__(self, config: Config) -> None:
        """Initialize results service.

        Args:
            config: Bot configuration
        """
        self.config = config

    def generate_results_content(
        self,
        batch: BatchData,
        votes: list[EstimationVote],
        vote_count: int,
        total_voters: int,
        batch_voters: list[str],
    ) -> str:
        """Generate the content for estimation results.

        Args:
            batch: Batch data
            votes: All votes for the batch
            vote_count: Number of voters who submitted votes
            total_voters: Total number of expected voters
            batch_voters: List of voters for this specific batch

        Returns:
            Formatted results content
        """
        # Group votes by issue
        votes_by_issue: dict[str, list[EstimationVote]] = {}
        for vote in votes:
            if vote.issue_number not in votes_by_issue:
                votes_by_issue[vote.issue_number] = []
            votes_by_issue[vote.issue_number].append(vote)

        all_voters = set(batch_voters)
        voted_voters = {vote.voter for vote in votes}
        non_voters = all_voters - voted_voters

        results_content = "🎲 **ESTIMATION RESULTS**\n\n"

        if non_voters:
            non_voter_mentions = ", ".join(f"@**{voter}**" for voter in sorted(non_voters))
            results_content += f"Note: {non_voter_mentions} didn't vote in this batch.\n\n"

        consensus_issues = []
        discussion_issues = []

        # Process each issue
        for issue in batch.issues:
            issue_votes = votes_by_issue.get(issue.issue_number, [])
            if not issue_votes:
                continue

            estimates = [vote.points for vote in issue_votes]
            estimates.sort()

            # Analyze consensus
            estimate_counts = Counter(estimates)
            most_common = estimate_counts.most_common()

            # Determine consensus vs discussion needed
            if len(most_common) == 1:
                # Perfect consensus
                final_estimate = most_common[0][0]
                consensus_issues.append((issue, estimates, final_estimate, "perfect"))
            elif len(estimates) >= 3:
                # Check for clustering
                sorted_estimates = sorted(estimates)
                clusters = self._find_clusters(sorted_estimates)

                if len(clusters) == 1 and len(clusters[0]) >= len(estimates) * 0.6:
                    # Strong cluster consensus
                    cluster = clusters[0]
                    final_estimate = max(cluster)  # Take highest in cluster for safety
                    consensus_issues.append((issue, estimates, final_estimate, "cluster"))
                else:
                    # Needs discussion
                    discussion_issues.append((issue, estimates, clusters))
            else:
                # Too few votes for meaningful analysis
                discussion_issues.append((issue, estimates, []))

        # Generate consensus section
        if consensus_issues:
            results_content += "✅ **CONSENSUS REACHED**\n"
            for issue, estimates, final_estimate, consensus_type in consensus_issues:
                estimates_str = ", ".join(map(str, estimates))
                if consensus_type == "perfect":
                    cluster_info = "(perfect consensus)"
                else:
                    cluster_info = f"({self._format_cluster_info(estimates, final_estimate)})"

                results_content += f"Issue {issue.issue_number} - {issue.title}\n"
                results_content += f"Estimates: {estimates_str}\n"
                results_content += (
                    f"Cluster: {cluster_info} | Final: **{final_estimate} points**\n\n"
                )

        # Generate discussion section
        if discussion_issues:
            results_content += "⚠️ **DISCUSSION NEEDED**\n"
            for issue, estimates, clusters in discussion_issues:
                estimates_str = ", ".join(map(str, estimates))
                results_content += f"Issue {issue.issue_number} - {issue.title}\n"
                results_content += f"Estimates: {estimates_str}\n"

                if len(clusters) > 1:
                    cluster_strs = []
                    for cluster in clusters:
                        cluster_strs.append(f"[{','.join(map(str, cluster))}]")
                    results_content += f"Clusters: {' vs '.join(cluster_strs)} - Mixed agreement\n"
                else:
                    results_content += "Wide spread - Needs discussion\n"

                # Add questions for voters with outlying estimates
                if estimates:
                    min_est, max_est = min(estimates), max(estimates)
                    if max_est - min_est > 5:  # Significant spread
                        high_voters = [
                            v.voter
                            for v in votes_by_issue[issue.issue_number]
                            if v.points == max_est
                        ]
                        low_voters = [
                            v.voter
                            for v in votes_by_issue[issue.issue_number]
                            if v.points == min_est
                        ]

                        if high_voters:
                            high_mentions = " @**".join(high_voters)
                            results_content += (
                                f"    @**{high_mentions}** : What complexity are you seeing "
                                f"that pushes this to {max_est}?\n"
                            )
                        if low_voters:
                            low_mentions = " @**".join(low_voters)
                            results_content += (
                                f"    @**{low_mentions}** : What's making this feel like "
                                f"a smaller story ({min_est} points)?\n"
                            )

                results_content += "\n"

        if discussion_issues:
            results_content += (
                "**🗣️ NEXT STEPS**\n"
                "Discussion phase for the disputed stories. Once discussion is complete, "
                "the facilitator should use the command:\n"
                "`finish #issue1: points rationale, #issue2: points rationale`\n\n"
                "Example: `finish #15116: 5 After discussion we agreed it's medium complexity, #15907: 3 Simple bug fix confirmed`\n"
            )

        return results_content

    def generate_finish_results(
        self,
        batch: BatchData,
        consensus_estimates: dict[str, int],
        final_estimates: list[FinalEstimate],
    ) -> str:
        """Generate the final results content after discussion is complete.

        Args:
            batch: Batch data
            consensus_estimates: Issues that had consensus from initial voting
            final_estimates: Final estimates after discussion

        Returns:
            Formatted final results content
        """
        results_content = "🎯 **ESTIMATION UPDATE - DISCUSSION COMPLETE**\n\n"
        results_content += (
            "Thanks everyone for the thoughtful discussion! Here are the final results:\n\n"
        )
        results_content += "**✅ FINAL ESTIMATES**\n\n"

        # Show consensus issues first
        for issue in batch.issues:
            issue_num = issue.issue_number
            if issue_num in consensus_estimates:
                points = consensus_estimates[issue_num]
                results_content += f"**Issue {issue_num}** - {issue.title}: **{points} points**\n"

        # Show discussed issues with rationale
        final_estimates_dict = {est.issue_number: est for est in final_estimates}
        for issue in batch.issues:
            issue_num = issue.issue_number
            if issue_num in final_estimates_dict:
                est = final_estimates_dict[issue_num]
                results_content += (
                    f"**Issue {issue_num}** - {issue.title}: **{est.final_points} points** "
                )
                if est.rationale:
                    results_content += f"({est.rationale})\n"
                else:
                    results_content += "(converged after discussion)\n"

        results_content += "\n**📝 ACTIONS**\n"
        results_content += "- Updating GitHub Projects with story points\n"
        results_content += "- Removing `needs-refinement` labels\n\n"
        results_content += "**🙏 THANKS**\n"
        results_content += "Appreciate the collaborative discussion - the outlier estimates led to valuable conversations!\n\n"
        results_content += "Next refinement batch coming [insert your next timeline].\n"

        return results_content

    def _find_clusters(self, sorted_estimates: list[int]) -> list[list[int]]:
        """Find clusters in sorted estimates using a simple gap-based approach."""
        if not sorted_estimates:
            return []

        clusters = [[sorted_estimates[0]]]

        for i in range(1, len(sorted_estimates)):
            current = sorted_estimates[i]
            previous = sorted_estimates[i - 1]

            # If gap is too large, start new cluster
            # Use Fibonacci gaps: 1->2 (gap 1), 2->3 (gap 1), 3->5 (gap 2), 5->8 (gap 3), etc.
            if current - previous > 2:
                clusters.append([current])
            else:
                clusters[-1].append(current)

        return clusters

    def _format_cluster_info(self, estimates: list[int], final_estimate: int) -> str:
        """Format cluster information for display."""
        clusters = self._find_clusters(sorted(estimates))

        if len(clusters) == 1:
            cluster = clusters[0]
            if len(set(cluster)) == 1:
                return "tight consensus"
            else:
                cluster_str = ",".join(map(str, sorted(set(cluster))))
                outliers = [est for est in estimates if est not in cluster]
                if outliers:
                    outlier_str = ",".join(map(str, sorted(set(outliers))))
                    return f"{cluster_str} (one {outlier_str} outlier)"
                else:
                    return f"{cluster_str} cluster"
        else:
            return "mixed clusters"
