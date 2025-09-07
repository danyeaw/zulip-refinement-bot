#!/usr/bin/env python3
"""Check that all migrations have corresponding tests."""

import re
import sys
from pathlib import Path


def check_migration_test_coverage() -> bool:
    """Check that all migrations have corresponding tests."""
    migrations_dir = Path("src/zulip_refinement_bot/migrations/versions")
    tests_dir = Path("tests")

    if not migrations_dir.exists():
        print("❌ Migrations directory not found")
        return False

    if not tests_dir.exists():
        print("❌ Tests directory not found")
        return False

    # Find all migration files
    migration_files = list(migrations_dir.glob("m*.py"))
    if not migration_files:
        print("✅ No migration files found")
        return True

    # Extract migration class names
    migration_classes = []
    for file_path in migration_files:
        content = file_path.read_text()
        class_pattern = re.compile(r"class\s+(\w+Migration)\s*\(.*Migration.*\):")
        class_match = class_pattern.search(content)

        if class_match:
            migration_classes.append(class_match.group(1))

    # Check test files for migration test coverage
    test_files = list(tests_dir.glob("**/test_*.py"))
    all_test_content = ""

    for test_file in test_files:
        try:
            all_test_content += test_file.read_text() + "\n"
        except Exception as e:
            print(f"⚠️  Could not read test file {test_file}: {e}")

    # Check coverage
    missing_tests = []
    for migration_class in migration_classes:
        # Look for test class or test methods that reference this migration
        test_patterns = [
            rf"class.*Test{migration_class}",
            rf"def.*test.*{migration_class.lower()}",
            rf"{migration_class}",
        ]

        found = any(
            re.search(pattern, all_test_content, re.IGNORECASE) for pattern in test_patterns
        )

        if not found:
            missing_tests.append(migration_class)

    if missing_tests:
        print("❌ Missing tests for migrations:")
        for migration_class in missing_tests:
            print(f"   - {migration_class}")
        print("\n💡 Consider adding tests in tests/test_migration_versions.py")
        return False

    print(f"✅ All {len(migration_classes)} migrations have test coverage")
    return True


if __name__ == "__main__":
    success = check_migration_test_coverage()
    sys.exit(0 if success else 1)
