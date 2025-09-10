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

            # Validate default voters before adding to database
            clean_voters = VoterValidationService.validate_voter_names(Config._default_voters)
            self.database.add_batch_voters(batch_id, clean_voters)

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
    ) -> tuple[dict[str, int], list[str], bool, bool]:
        """Submit votes and/or abstentions for a batch.

        Args:
            content: Vote content
            voter: Name of the voter
            batch: Active batch data

        Returns:
            Tuple of (estimates, abstentions, has_updates, all_voters_complete)

        Raises:
            AuthorizationError: If voter is not authorized
            ValidationError: If vote validation fails
            VotingError: If vote storage fails
        """
        if batch.id is None:
            raise VotingError("No active batch found. Cannot submit votes.")

        batch_voters = self.database.get_batch_voters(batch.id)
        if voter not in batch_voters:
            clean_voter = VoterValidationService.validate_voter_name(voter)
            was_added = self.database.add_voter_to_batch(batch.id, clean_voter)
            if was_added:
                logger.info("Added new voter to batch", batch_id=batch.id, voter=clean_voter)

        estimates, abstentions, validation_errors = self.parser.parse_estimation_input(content)

        if validation_errors:
            error_msg = "Invalid values found:\n"
            for error in validation_errors:
                error_msg += f"  • {error}\n"
            error_msg += "\nValid story points (Fibonacci sequence): 1, 2, 3, 5, 8, 13, 21\nOr use 'abstain' to abstain from voting"
            raise ValidationError(error_msg)

        if not estimates and not abstentions:
            raise ValidationError(
                "No valid votes or abstentions found. Please use format: `#1234: 5, #1235: 8, #1236: abstain`\n"
                "Valid story points: 1, 2, 3, 5, 8, 13, 21\nOr use 'abstain' to abstain from voting"
            )

        self._validate_vote_completeness(estimates, abstentions, batch)

        stored_count, updated_count, new_count = self._store_votes_and_abstentions(
            batch.id, voter, estimates, abstentions
        )

        expected_count = len(estimates) + len(abstentions)
        if stored_count != expected_count:
            raise VotingError(
                f"Only {stored_count} out of {expected_count} votes/abstentions were processed successfully."
            )

        completed_voters_count = self.database.get_completed_voters_count(batch.id)
        batch_voters = self.database.get_batch_voters(batch.id)
        all_voters_complete = completed_voters_count >= len(batch_voters)

        logger.info(
            "Votes and abstentions submitted successfully",
            batch_id=batch.id,
            voter=voter,
            new_votes=new_count,
            updated_votes=updated_count,
            abstentions_count=len(abstentions),
            all_voters_complete=all_voters_complete,
        )

        return estimates, abstentions, stored_count > 0, all_voters_complete

    def _validate_vote_completeness(
        self, estimates: dict[str, int], abstentions: list[str], batch: BatchData
    ) -> None:
        """Validate that all batch issues are voted on or abstained from.

        Args:
            estimates: Vote estimates
            abstentions: List of issue numbers abstained from
            batch: Batch data

        Raises:
            ValidationError: If vote validation fails
        """
        batch_issue_numbers = {issue.issue_number for issue in batch.issues}
        vote_issue_numbers = set(estimates.keys())
        abstention_issue_numbers = set(abstentions)
        all_addressed_issues = vote_issue_numbers | abstention_issue_numbers

        # Check for duplicates between votes and abstentions
        overlap = vote_issue_numbers & abstention_issue_numbers
        if overlap:
            overlap_list = ", ".join([f"#{issue}" for issue in sorted(overlap)])
            raise ValidationError(
                f"Cannot both vote and abstain on the same issues: {overlap_list}\n"
                "Please choose either a vote or abstention for each issue."
            )

        missing_issues = batch_issue_numbers - all_addressed_issues
        extra_issues = all_addressed_issues - batch_issue_numbers

        if missing_issues or extra_issues:
            error_msg = "Vote validation failed:\n"
            if missing_issues:
                missing_list = ", ".join(f"#{num}" for num in missing_issues)
                error_msg += f"Missing votes/abstentions for issues: {missing_list}\n"
            if extra_issues:
                extra_list = ", ".join(f"#{num}" for num in extra_issues)
                error_msg += f"Votes/abstentions for issues not in batch: {extra_list}\n"

            required_list = ", ".join(f"#{num}" for num in batch_issue_numbers)
            error_msg += f"\nPlease vote or abstain for exactly these issues: {required_list}"
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

    def _store_votes_and_abstentions(
        self, batch_id: int, voter: str, estimates: dict[str, int], abstentions: list[str]
    ) -> tuple[int, int, int]:
        """Store votes and abstentions in the database.

        Args:
            batch_id: Batch ID
            voter: Voter name
            estimates: Vote estimates
            abstentions: List of issue numbers to abstain from

        Returns:
            Tuple of (stored_count, updated_count, new_count)
        """
        stored_count = 0
        updated_count = 0
        new_count = 0

        # Store votes
        for issue_number, points in estimates.items():
            # Remove any existing abstention for this issue
            self.database.remove_abstention_if_exists(batch_id, voter, issue_number)

            success, was_update = self.database.upsert_vote(batch_id, voter, issue_number, points)
            if success:
                stored_count += 1
                if was_update:
                    updated_count += 1
                else:
                    new_count += 1

        # Store abstentions
        for issue_number in abstentions:
            # Remove any existing vote for this issue
            self.database.remove_vote_if_exists(batch_id, voter, issue_number)

            success, was_update = self.database.upsert_abstention(batch_id, voter, issue_number)
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
            Tuple of (completed_count, total_voters, is_complete)
        """
        completed_count = self.database.get_completed_voters_count(batch_id)
        batch_voters = self.database.get_batch_voters(batch_id)
        total_voters = len(batch_voters)
        is_complete = completed_count >= total_voters

        return completed_count, total_voters, is_complete


class ResultsService:
    """Service for generating and analyzing estimation results."""

    def __init__(self, config: Config, github_api: GitHubAPIInterface) -> None:
        """Initialize results service.

        Args:
            config: Bot configuration
            github_api: GitHub API interface
        """
        self.config = config
        self.github_api = github_api

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

                title = (
                    self.github_api.fetch_issue_title_by_url(issue.url)
                    or f"Issue {issue.issue_number}"
                )
                results_content += f"Issue {issue.issue_number} - {title}\n"
                results_content += f"Estimates: {estimates_str}\n"
                results_content += (
                    f"Cluster: {cluster_info} | Final: **{final_estimate} points**\n\n"
                )

        # Generate discussion section
        if discussion_issues:
            results_content += "⚠️ **DISCUSSION NEEDED**\n"
            for issue, estimates, clusters in discussion_issues:
                estimates_str = ", ".join(map(str, estimates))
                title = (
                    self.github_api.fetch_issue_title_by_url(issue.url)
                    or f"Issue {issue.issue_number}"
                )
                results_content += f"Issue {issue.issue_number} - {title}\n"
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
                    # Lower threshold for discussion questions - any spread >= 3 or multiple clusters
                    should_ask_questions = (max_est - min_est >= 3) or (len(clusters) > 1)
                    if should_ask_questions:
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
                            if len(clusters) > 1:
                                results_content += (
                                    f"    @**{high_mentions}** : What complexity or risks are you seeing "
                                    f"that justify {max_est} points over the {min_est}-{sorted(estimates)[len(estimates) // 2]} point estimates?\n"
                                )
                            else:
                                results_content += (
                                    f"    @**{high_mentions}** : What complexity are you seeing "
                                    f"that pushes this to {max_est} points?\n"
                                )
                        if low_voters:
                            low_mentions = " @**".join(low_voters)
                            if len(clusters) > 1:
                                results_content += (
                                    f"    @**{low_mentions}** : What makes this feel simpler "
                                    f"({min_est} points) compared to the {max_est} point estimates?\n"
                                )
                            else:
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
                title = (
                    self.github_api.fetch_issue_title_by_url(issue.url)
                    or f"Issue {issue.issue_number}"
                )
                results_content += f"**Issue {issue_num}** - {title}: **{points} points**\n"

        # Show discussed issues with rationale
        final_estimates_dict = {est.issue_number: est for est in final_estimates}
        for issue in batch.issues:
            issue_num = issue.issue_number
            if issue_num in final_estimates_dict:
                est = final_estimates_dict[issue_num]
                title = (
                    self.github_api.fetch_issue_title_by_url(issue.url)
                    or f"Issue {issue.issue_number}"
                )
                results_content += (
                    f"**Issue {issue_num}** - {title}: **{est.final_points} points** "
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


class VoterValidationService:
    """Service for validating voter names and input."""

    @staticmethod
    def validate_voter_name(voter: str) -> str:
        """Validate and clean a voter name.

        Args:
            voter: Raw voter name input

        Returns:
            Clean voter name

        Raises:
            ValidationError: If voter name is invalid
        """
        if not voter or not voter.strip():
            raise ValidationError("Voter name cannot be empty")

        clean_voter = voter.strip()

        if "#" in clean_voter or ":" in clean_voter or "`" in clean_voter:
            raise ValidationError(
                f"Invalid voter name '{voter}' - contains characters that suggest vote data corruption"
            )

        return clean_voter

    @staticmethod
    def validate_voter_names(voters: list[str]) -> list[str]:
        """Validate and clean a list of voter names.

        Args:
            voters: List of raw voter name inputs

        Returns:
            List of clean voter names (empty names filtered out)

        Raises:
            ValidationError: If any voter name is invalid
        """
        clean_voters = []

        for voter in voters:
            if not voter or not voter.strip():
                continue

            try:
                clean_voter = VoterValidationService.validate_voter_name(voter)
                if clean_voter not in clean_voters:
                    clean_voters.append(clean_voter)
            except ValidationError as e:
                logger.warning("Skipping invalid voter name", voter=voter, error=str(e))
                continue

        return clean_voters
