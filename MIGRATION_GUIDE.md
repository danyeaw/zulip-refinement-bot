# Database Migration System

Structured database schema management for the Zulip Refinement Bot.

## Features

- Version tracking with unique numbers
- Dependency management between migrations
- Optional rollback support
- Schema validation
- CLI tools for management

## Quick Start

```python
from migrations.base import Migration, SchemaValidationMixin

class MyMigration(Migration, SchemaValidationMixin):
    @property
    def version(self) -> str:
        return "005"

    @property
    def description(self) -> str:
        return "Add new feature table"

    def up(self, conn: sqlite3.Connection) -> None:
        self.execute_sql(conn, "CREATE TABLE ...")

    def down(self, conn: sqlite3.Connection) -> None:
        self.execute_sql(conn, "DROP TABLE ...")

    def validate(self, conn: sqlite3.Connection) -> bool:
        return self.table_exists(conn, "my_table")
```

## CLI Commands

```bash
zulip-refinement-bot migrate status     # Show status
zulip-refinement-bot migrate run        # Run pending
zulip-refinement-bot migrate run 003    # Run to version
zulip-refinement-bot migrate run --dry-run  # Preview
zulip-refinement-bot migrate rollback 004   # Rollback
zulip-refinement-bot migrate validate   # Validate all
zulip-refinement-bot migrate init       # Initialize DB
```

## Programmatic Usage

```python
from pathlib import Path
from migrations.runner import MigrationRunner
from migrations.versions import ALL_MIGRATIONS

runner = MigrationRunner(Path("data/refinement.db"))
runner.register_migrations(ALL_MIGRATIONS)
runner.run_migrations()
```

## Creating Migrations

1. **Create file**: `migrations/versions/m005_add_comments.py`
2. **Register**: Add to `migrations/versions/__init__.py`
3. **Test**: Run `migrate run --dry-run` then `migrate run`

Example:
```python
class AddCommentsMigration(Migration, SchemaValidationMixin):
    @property
    def version(self) -> str:
        return "005"

    @property
    def description(self) -> str:
        return "Add comments table"

    def up(self, conn: sqlite3.Connection) -> None:
        self.execute_sql(conn, "CREATE TABLE comments (...)")

    def down(self, conn: sqlite3.Connection) -> None:
        self.execute_sql(conn, "DROP TABLE IF EXISTS comments")

    def validate(self, conn: sqlite3.Connection) -> bool:
        return self.table_exists(conn, "comments")
```

## Best Practices

- **Sequential numbering**: `m001`, `m002`, etc.
- **Idempotent**: Use `IF NOT EXISTS` clauses
- **Include rollback**: Implement `down()` method when possible
- **Add validation**: Implement `validate()` method
- **Test thoroughly**: Test both up and down migrations
- **Backup first**: Always backup production data before migrations

## Common Patterns

**Add Column:**
```python
def up(self, conn: sqlite3.Connection) -> None:
    self.execute_sql(conn, "ALTER TABLE batches ADD COLUMN priority INTEGER DEFAULT 1")
```

**Add Index:**
```python
def up(self, conn: sqlite3.Connection) -> None:
    self.execute_sql(conn, "CREATE INDEX IF NOT EXISTS idx_votes_created_at ON votes(created_at)")
```

**Data Migration:**
```python
def up(self, conn: sqlite3.Connection) -> None:
    self.execute_sql(conn, "ALTER TABLE issues ADD COLUMN priority INTEGER")
    self.execute_sql(conn, "UPDATE issues SET priority = 1 WHERE title LIKE '%urgent%'")
```

## Troubleshooting

**Migration fails**: Check logs for SQL errors
**Rollback fails**: Fix rollback logic, may need manual cleanup
**Validation fails**: Ensure validation matches migration changes

**Debug logging:**
```python
import structlog
structlog.configure(level="DEBUG")
```
