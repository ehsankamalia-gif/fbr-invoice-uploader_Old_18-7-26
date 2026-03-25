
# Deployment and Environment Setup System

This document describes the robust deployment system designed to automatically set up the application environment on any new machine.

## Architecture Overview

The system consists of three main layers that execute in sequence before the application GUI launches:

1.  **Bootstrapper ([bootstrap.py](file:///c:/laragon/www/fbr-invoice-uploader/app/core/bootstrap.py))**:
    *   **Dependency Management**: Checks `requirements.txt` and automatically installs missing Python packages using `pip`.
    *   **Directory Setup**: Creates essential application folders (`logs`, `backups`, `temp`, `exports`).
    *   **Configuration Setup**: Automatically creates a `.env` file from `.env.example` if it doesn't exist.
    *   **Cross-Platform**: Supports Windows, Linux, and macOS.

2.  **Deployment Orchestrator ([deployment.py](file:///c:/laragon/www/fbr-invoice-uploader/app/core/deployment.py))**:
    *   Coordinates the bootstrapping process with database initialization.
    *   Ensures that the environment is fully ready before the main application logic imports any dependencies.

3.  **Self-Healing Database ([session.py](file:///c:/laragon/www/fbr-invoice-uploader/app/db/session.py))**:
    *   **Schema Integrity**: Automatically detects missing tables or columns by comparing the actual database schema with the SQLAlchemy models.
    *   **Automatic Repair**: Dynamically executes `ALTER TABLE` statements to add missing columns without losing existing data.
    *   **Versioned Migrations**: Continues to support version-based migrations for complex structural changes.

## Execution Flow

When a user runs the application (via `python -m app.main` or the executable):

1.  `app/main.py` is the entry point.
2.  It immediately triggers `run_bootstrap()`.
3.  If dependencies are missing, a console-based progress log appears while `pip` installs them.
4.  Once the environment is verified, the main Qt application is imported and launched.
5.  `init_db()` runs, performing schema integrity checks and applying any necessary migrations.

## Maintenance Requirements

### Adding New Dependencies
*   Always add new packages to `requirements.txt`.
*   The system will automatically detect and install them on all client machines during the next launch.

### Adding New Database Columns
*   Simply update the models in `app/db/models.py`.
*   The `verify_schema_integrity` system will automatically detect the new columns and add them to the database on the next launch.
*   For complex changes (e.g., changing a column type or moving data), use the versioned migration system in `app/db/session.py`.

### Logging
*   All deployment and bootstrapping logs are saved to `logs/app.log` (once the logger is initialized) or printed to the standard output during early bootstrapping.

## Automated Testing
*   Run `python tests/test_deployment_system.py` to verify the setup logic in a clean, temporary environment.
