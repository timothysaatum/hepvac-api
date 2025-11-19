#!/usr/bin/env python
"""
Unified migration management script.

Usage:
    python run_migrate.py create "migration message"  # Create new migration
    python run_migrate.py upgrade                     # Apply all pending migrations
    python run_migrate.py downgrade                   # Rollback one migration
    python run_migrate.py current                     # Show current migration
    python run_migrate.py history                     # Show migration history
"""
from alembic.config import Config
from alembic import command
import os
import sys


# Path to alembic.ini
alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))


def create_migration(message: str):
    """Generate a new migration file."""
    try:
        command.revision(alembic_cfg, message=message, autogenerate=True)
        print(f"Migration '{message}' created successfully")
        print("   Run 'python run_migrate.py upgrade' to apply it")
    except Exception as e:
        print(f"Error creating migration: {str(e)}")
        sys.exit(1)


def upgrade_migrations(revision: str = "head"):
    """Apply migrations up to the specified revision."""
    try:
        print(f"Upgrading database to: {revision}")
        command.upgrade(alembic_cfg, revision)
        print("Database upgraded successfully")
    except Exception as e:
        print(f"Error upgrading database: {str(e)}")
        sys.exit(1)


def downgrade_migrations(revision: str = "-1"):
    """Rollback migrations to the specified revision."""
    try:
        print(f"Downgrading database to: {revision}")
        command.downgrade(alembic_cfg, revision)
        print("Database downgraded successfully")
    except Exception as e:
        print(f"Error downgrading database: {str(e)}")
        sys.exit(1)


def show_current():
    """Show current migration version."""
    try:
        command.current(alembic_cfg)
    except Exception as e:
        print(f"Error showing current version: {str(e)}")
        sys.exit(1)


def show_history():
    """Show migration history."""
    try:
        command.history(alembic_cfg)
    except Exception as e:
        print(f"Error showing history: {str(e)}")
        sys.exit(1)


def print_usage():
    """Print usage information."""
    print(__doc__)


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    action = sys.argv[1].lower()

    if action == "create":
        if len(sys.argv) < 3:
            print("Error: Migration message required")
            print("   Usage: python run_migrate.py create 'migration message'")
            sys.exit(1)
        message = sys.argv[2]
        create_migration(message)

    elif action == "upgrade":
        revision = sys.argv[2] if len(sys.argv) > 2 else "head"
        upgrade_migrations(revision)

    elif action == "downgrade":
        revision = sys.argv[2] if len(sys.argv) > 2 else "-1"
        downgrade_migrations(revision)

    elif action == "current":
        show_current()

    elif action == "history":
        show_history()

    else:
        print(f"Unknown action: {action}")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
