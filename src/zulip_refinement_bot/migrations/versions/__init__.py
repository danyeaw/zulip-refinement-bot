"""Migration versions for the Zulip Refinement Bot."""

from .m001_initial_schema import InitialSchemaMigration
from .m002_add_message_id import AddMessageIdMigration
from .m003_batch_voters import BatchVotersMigration
from .m004_final_estimates import FinalEstimatesMigration

# All migrations in order
ALL_MIGRATIONS = [
    InitialSchemaMigration,
    AddMessageIdMigration,
    BatchVotersMigration,
    FinalEstimatesMigration,
]

__all__ = [
    "InitialSchemaMigration",
    "AddMessageIdMigration",
    "BatchVotersMigration",
    "FinalEstimatesMigration",
    "ALL_MIGRATIONS",
]
