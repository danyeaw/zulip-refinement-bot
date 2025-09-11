"""Migration versions for the Zulip Refinement Bot."""

from .m001_initial_schema import InitialSchemaMigration
from .m002_add_message_id import AddMessageIdMigration
from .m003_batch_voters import BatchVotersMigration
from .m004_final_estimates import FinalEstimatesMigration
from .m005_remove_title_column import RemoveTitleColumnMigration
from .m006_add_abstentions import AddAbstentionsMigration
from .m007_add_reminders import AddRemindersMigration
from .m008_add_results_message_id import AddResultsMessageIdMigration

# All migrations in order
ALL_MIGRATIONS = [
    InitialSchemaMigration,
    AddMessageIdMigration,
    BatchVotersMigration,
    FinalEstimatesMigration,
    RemoveTitleColumnMigration,
    AddAbstentionsMigration,
    AddRemindersMigration,
    AddResultsMessageIdMigration,
]

__all__ = [
    "InitialSchemaMigration",
    "AddMessageIdMigration",
    "BatchVotersMigration",
    "FinalEstimatesMigration",
    "RemoveTitleColumnMigration",
    "AddAbstentionsMigration",
    "AddRemindersMigration",
    "AddResultsMessageIdMigration",
    "ALL_MIGRATIONS",
]
