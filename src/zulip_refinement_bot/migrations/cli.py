# mypy: disable-error-code=misc

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .runner import MigrationRunner
from .versions import ALL_MIGRATIONS

console = Console()
app = typer.Typer(name="migrate", help="Database migration commands")


def get_migration_runner(db_path: Path | None = None) -> MigrationRunner:
    if db_path is None:
        db_path = Path("data/refinement.db")

    runner = MigrationRunner(db_path)
    runner.register_migrations(ALL_MIGRATIONS)
    return runner


@app.command()
def status(
    db_path: Path | None = typer.Option(None, "--db-path", help="Path to database file"),
) -> None:
    runner = get_migration_runner(db_path)
    status_info = runner.get_migration_status()

    if not status_info:
        console.print("No migrations registered.", style="yellow")
        return

    table = Table(title="Migration Status")
    table.add_column("Version", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Description", style="white")
    table.add_column("Applied At", style="dim")
    table.add_column("Rollback", style="magenta")

    for version, info in status_info.items():
        rollback_text = "✓" if info["can_rollback"] else "✗"
        rollback_style = "green" if info["can_rollback"] else "red"

        table.add_row(
            version,
            info["status"],
            info["description"],
            info.get("applied_at", ""),
            f"[{rollback_style}]{rollback_text}[/{rollback_style}]",
        )

    console.print(table)


@app.command()
def run(
    target_version: str | None = typer.Argument(None, help="Target migration version"),
    db_path: Path | None = typer.Option(None, "--db-path", help="Path to database file"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be executed without running"
    ),
) -> None:
    runner = get_migration_runner(db_path)

    try:
        applied = runner.run_migrations(target_version=target_version, dry_run=dry_run)

        if not applied:
            console.print("No migrations to run.", style="green")
        elif dry_run:
            console.print(f"Would apply {len(applied)} migrations:", style="yellow")
            for version in applied:
                console.print(f"  - {version}", style="dim")
        else:
            console.print(f"Successfully applied {len(applied)} migrations:", style="green")
            for version in applied:
                console.print(f"  ✓ {version}", style="green")

    except Exception as e:
        console.print(f"Migration failed: {e}", style="red")
        raise typer.Exit(1) from e


@app.command()
def rollback(
    version: str = typer.Argument(..., help="Migration version to rollback"),
    db_path: Path | None = typer.Option(None, "--db-path", help="Path to database file"),
    confirm: bool = typer.Option(False, "--yes", help="Skip confirmation prompt"),
) -> None:
    runner = get_migration_runner(db_path)

    if not confirm:
        confirmed = typer.confirm(f"Are you sure you want to rollback migration {version}?")
        if not confirmed:
            console.print("Rollback cancelled.", style="yellow")
            return

    try:
        runner.rollback_migration(version)
        console.print(f"Successfully rolled back migration {version}", style="green")
    except Exception as e:
        console.print(f"Rollback failed: {e}", style="red")
        raise typer.Exit(1) from e


@app.command()
def validate(
    db_path: Path | None = typer.Option(None, "--db-path", help="Path to database file"),
) -> None:
    runner = get_migration_runner(db_path)

    try:
        is_valid = runner.validate_migrations()
        if is_valid:
            console.print("All migrations are valid ✓", style="green")
        else:
            console.print("Some migrations failed validation ✗", style="red")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"Validation failed: {e}", style="red")
        raise typer.Exit(1) from e


@app.command()
def init(
    db_path: Path | None = typer.Option(None, "--db-path", help="Path to database file"),
) -> None:
    runner = get_migration_runner(db_path)

    console.print("Initializing database with all migrations...", style="blue")

    try:
        applied = runner.run_migrations()
        console.print(f"Database initialized with {len(applied)} migrations ✓", style="green")
    except Exception as e:
        console.print(f"Database initialization failed: {e}", style="red")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
