#!/usr/bin/env python3
"""Check that migration versions are sequential and properly formatted."""

import re
import sys
from pathlib import Path


def check_migration_versions() -> bool:
    """Check migration version sequence and formatting."""
    migrations_dir = Path("src/zulip_refinement_bot/migrations/versions")

    if not migrations_dir.exists():
        print("❌ Migrations directory not found")
        return False

    # Find all migration files
    migration_files = list(migrations_dir.glob("m*.py"))
    if not migration_files:
        print("✅ No migration files found")
        return True

    # Extract version numbers
    versions = []
    version_pattern = re.compile(r"m(\d{3})_.*\.py")

    for file_path in migration_files:
        match = version_pattern.match(file_path.name)
        if not match:
            print(f"❌ Invalid migration filename format: {file_path.name}")
            print("   Expected format: mXXX_description.py (e.g., m001_initial_schema.py)")
            return False

        version = int(match.group(1))
        versions.append((version, file_path))

    # Sort by version number
    versions.sort(key=lambda x: x[0])

    # Check for sequential versions
    expected_version = 1
    for version, file_path in versions:
        if version != expected_version:
            print("❌ Migration version gap detected!")
            print(f"   Expected version {expected_version:03d}, found {version:03d}")
            print(f"   File: {file_path.name}")
            return False
        expected_version += 1

    # Check that each migration file has proper class naming
    for version, file_path in versions:
        content = file_path.read_text()

        # Check for class definition
        class_pattern = re.compile(r"class\s+(\w+)\s*\(.*Migration.*\):")
        class_match = class_pattern.search(content)

        if not class_match:
            print(f"❌ No Migration class found in {file_path.name}")
            return False

        class_name = class_match.group(1)

        # Check class name follows convention
        if not class_name.endswith("Migration"):
            print(f"❌ Migration class name should end with 'Migration': {class_name}")
            print(f"   File: {file_path.name}")
            return False

        # Check version property
        version_property_pattern = re.compile(
            r'def version\(self\) -> str:\s*return\s*["\'](\d{3})["\']'
        )
        version_match = version_property_pattern.search(content)

        if not version_match:
            print(f"❌ Invalid or missing version property in {file_path.name}")
            return False

        declared_version = int(version_match.group(1))
        if declared_version != version:
            print(f"❌ Version mismatch in {file_path.name}")
            print(
                f"   Filename indicates version {version:03d}, "
                f"class declares {declared_version:03d}"
            )
            return False

    print(
        f"✅ Migration versions are sequential and properly formatted ({len(versions)} migrations)"
    )
    return True


if __name__ == "__main__":
    success = check_migration_versions()
    sys.exit(0 if success else 1)
