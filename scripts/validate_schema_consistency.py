#!/usr/bin/env python3
"""Validate database schema consistency across migrations and models."""

import ast
import re
import sys
from pathlib import Path


def extract_table_definitions_from_migrations() -> dict[str, set[str]]:
    """Extract table definitions from migration files."""
    migrations_dir = Path("src/zulip_refinement_bot/migrations/versions")
    tables: dict[str, set[str]] = {}

    if not migrations_dir.exists():
        return tables

    # Process migrations in order
    migration_files = sorted(migrations_dir.glob("m*.py"))

    for file_path in migration_files:
        content = file_path.read_text()

        # Find CREATE TABLE statements - handle nested parentheses
        def extract_table_definitions(content: str) -> list[tuple[str, str]]:
            """Extract table definitions handling nested parentheses properly."""
            tables = []
            pattern = re.compile(
                r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\(", re.IGNORECASE
            )

            for match in pattern.finditer(content):
                table_name = match.group(1)
                start_pos = match.end() - 1  # Position of opening parenthesis

                # Find matching closing parenthesis
                paren_count = 0
                pos = start_pos
                while pos < len(content):
                    if content[pos] == "(":
                        paren_count += 1
                    elif content[pos] == ")":
                        paren_count -= 1
                        if paren_count == 0:
                            # Found matching closing parenthesis
                            table_def = content[start_pos + 1 : pos]  # Content between parentheses
                            tables.append((table_name, table_def))
                            break
                    pos += 1

            return tables

        table_definitions = extract_table_definitions(content)

        for table_name, columns_def in table_definitions:
            # Extract column names (improved parsing)
            # Split by commas first
            column_parts = columns_def.split(",")
            columns = set()

            for part in column_parts:
                # Clean up the part
                part = part.strip()
                if not part:
                    continue

                # Remove newlines and extra whitespace
                part = " ".join(part.split())

                # Skip constraint definitions
                if part.upper().startswith(
                    ("FOREIGN KEY", "UNIQUE(", "PRIMARY KEY", "CHECK", "CONSTRAINT")
                ):
                    continue

                # Extract first word as column name
                words = part.split()
                if words:
                    col_name = words[0].strip()
                    # Remove any quotes or special characters
                    col_name = col_name.strip("\"'`()")
                    if col_name and col_name.upper() not in [
                        "FOREIGN",
                        "UNIQUE",
                        "PRIMARY",
                        "CHECK",
                        "CONSTRAINT",
                    ]:
                        columns.add(col_name)

            if table_name not in tables:
                tables[table_name] = set()
            tables[table_name].update(columns)

        # Find ALTER TABLE ADD COLUMN statements
        alter_table_pattern = re.compile(
            r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)", re.IGNORECASE
        )

        for match in alter_table_pattern.finditer(content):
            table_name = match.group(1)
            column_name = match.group(2)

            if table_name not in tables:
                tables[table_name] = set()
            tables[table_name].add(column_name)

    return tables


def extract_model_fields() -> dict[str, set[str]]:
    """Extract field definitions from Pydantic models."""
    models_file = Path("src/zulip_refinement_bot/models.py")

    if not models_file.exists():
        return {}

    content = models_file.read_text()

    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        print(f"❌ Could not parse models.py: {e}")
        return {}

    models = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check if it's a Pydantic model (inherits from BaseModel)
            is_model = any(
                isinstance(base, ast.Name) and base.id == "BaseModel" for base in node.bases
            )

            if is_model:
                class_name = node.name
                fields = set()

                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        field_name = item.target.id
                        fields.add(field_name)

                models[class_name] = fields

    return models


def map_models_to_tables() -> dict[str, str]:
    """Map model names to database table names."""
    # This is a simplified mapping - in practice you might need more sophisticated logic
    mapping = {
        "BatchData": "batches",
        "IssueData": "issues",
        "EstimationVote": "votes",
        "FinalEstimate": "final_estimates",
        # batch_voters doesn't have a direct model (it's a join table)
    }
    return mapping


def get_model_field_exclusions() -> dict[str, set[str]]:
    """Get fields that should be excluded from validation (relationships, computed fields, etc.)."""
    return {
        "BatchData": {"issues"},  # issues is a relationship field, not a database column
        "EstimationVote": set(),
        "IssueData": set(),
        "FinalEstimate": set(),
    }


def get_database_column_exclusions() -> dict[str, set[str]]:
    """Get database columns that don't need to be in models (auto-generated, foreign keys, etc.)."""
    return {
        "batches": set(),  # BatchData model has all the fields
        "issues": {"id", "batch_id"},  # id is auto, batch_id is foreign key
        "votes": {
            "id",
            "batch_id",
        },  # id is auto, batch_id is foreign key (created_at maps to timestamp)
        "final_estimates": {"id", "batch_id"},  # id and batch_id are not in model
        "batch_voters": {"id", "batch_id"},  # Join table
    }


def get_field_mappings() -> dict[str, dict[str, str]]:
    """Get field name mappings between models and database columns."""
    return {
        "EstimationVote": {"timestamp": "created_at"},  # timestamp field maps to created_at column
        "FinalEstimate": {},  # timestamp field exists in both
    }


def validate_schema_consistency() -> None:
    """Validate that database schema matches model definitions."""
    print("🔍 Validating database schema consistency...")

    # Extract information
    migration_tables = extract_table_definitions_from_migrations()
    model_fields = extract_model_fields()
    model_table_mapping = map_models_to_tables()
    field_exclusions = get_model_field_exclusions()
    column_exclusions = get_database_column_exclusions()
    field_mappings = get_field_mappings()

    if not migration_tables:
        print("⚠️  No migration tables found")
        return

    if not model_fields:
        print("⚠️  No model fields found")
        return

    print(f"📊 Found {len(migration_tables)} tables in migrations")
    print(f"📊 Found {len(model_fields)} models")

    success = True

    # Check each model against its corresponding table
    for model_name, table_name in model_table_mapping.items():
        if model_name not in model_fields:
            print(f"⚠️  Model {model_name} not found in models.py")
            continue

        if table_name not in migration_tables:
            print(f"❌ Table {table_name} not found in migrations (required by {model_name})")
            success = False
            continue

        # Apply exclusions and mappings
        model_field_set = model_fields[model_name] - field_exclusions.get(model_name, set())
        table_column_set = migration_tables[table_name] - column_exclusions.get(table_name, set())

        # Apply field mappings (convert model field names to expected column names)
        mappings = field_mappings.get(model_name, {})
        mapped_model_fields = set()
        for field in model_field_set:
            mapped_name = mappings.get(field, field)
            mapped_model_fields.add(mapped_name)

        # Check for missing columns (fields in model but not in table)
        missing_columns = mapped_model_fields - table_column_set
        if missing_columns:
            print(f"❌ {model_name} -> {table_name}: Missing columns in database:")
            for col in sorted(missing_columns):
                print(f"   - {col}")
            success = False

        # Check for extra columns (columns in table but not in model)
        extra_columns = table_column_set - mapped_model_fields
        if extra_columns:
            print(f"ℹ️  {model_name} -> {table_name}: Extra columns in database (may be expected):")
            for col in sorted(extra_columns):
                print(f"   - {col}")

    # Check for tables without corresponding models
    mapped_tables = set(model_table_mapping.values())
    # Exclude system tables and temporary tables used in migrations
    system_tables = {"schema_migrations", "sqlite_sequence"}
    temp_table_patterns = {"_new", "_old", "_temp", "_backup"}

    unmapped_tables = set(migration_tables.keys()) - mapped_tables - system_tables

    # Filter out temporary tables (used in rollbacks)
    permanent_unmapped_tables = []
    for table in unmapped_tables:
        is_temp = any(pattern in table for pattern in temp_table_patterns)
        if not is_temp:
            permanent_unmapped_tables.append(table)

    if permanent_unmapped_tables:
        print("ℹ️  Tables without corresponding models:")
        for table in sorted(permanent_unmapped_tables):
            print(f"   - {table}")

    # Show temporary tables separately for debugging
    temp_tables = [
        table
        for table in unmapped_tables
        if any(pattern in table for pattern in temp_table_patterns)
    ]
    if temp_tables:
        print("🔧 Temporary tables found in migrations (used for rollbacks):")
        for table in sorted(temp_tables):
            print(f"   - {table}")

    if success:
        print("✅ Database schema is consistent with models")
    else:
        print("❌ Database schema inconsistencies found")
        sys.exit(1)


def check_migration_rollback_safety() -> None:
    """Check that migrations implement proper rollback methods."""
    migrations_dir = Path("src/zulip_refinement_bot/migrations/versions")

    if not migrations_dir.exists():
        return

    migration_files = list(migrations_dir.glob("m*.py"))
    issues = []

    for file_path in migration_files:
        content = file_path.read_text()

        # Check if down() method is implemented
        down_method_pattern = re.compile(r"def\s+down\s*\(.*?\):", re.MULTILINE)
        has_down_method = down_method_pattern.search(content) is not None

        if has_down_method:
            # Check if it's just raising NotImplementedError
            not_implemented_pattern = re.compile(
                r"def\s+down\s*\(.*?\):.*?raise\s+NotImplementedError", re.DOTALL
            )
            is_not_implemented = not_implemented_pattern.search(content) is not None

            if is_not_implemented:
                issues.append(f"{file_path.name}: down() method raises NotImplementedError")
        else:
            issues.append(f"{file_path.name}: missing down() method")

    if issues:
        print("⚠️  Migration rollback issues:")
        for issue in issues:
            print(f"   - {issue}")
        print("💡 Consider implementing rollback methods for production safety")


if __name__ == "__main__":
    try:
        validate_schema_consistency()
        check_migration_rollback_safety()
    except Exception as e:
        print(f"❌ Schema validation failed with error: {e}")
        sys.exit(1)

    sys.exit(0)
