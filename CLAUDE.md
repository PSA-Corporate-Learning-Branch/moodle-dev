# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Docker-based Moodle 4.5 development environment for BC Gov PSA. Contains two custom components mounted as volumes for active development:

- **psaelmsync** (`plugins/psaelmsync/`) - Local plugin that syncs enrollment data from ELM (Enterprise Learning Management) and sends completion data back via CData API
- **bcgovpsa** (`themes/bcgovpsa/`) - Boost child theme for BC Gov PSA branding

## Development Commands

```bash
# Start environment
docker compose up -d

# Stop environment
docker compose down

# Rebuild after Dockerfile changes
docker compose build moodle && docker compose down && docker compose up -d

# Access container shell
docker compose exec moodle bash

# Run Moodle upgrade (after plugin changes)
docker compose exec moodle php /var/www/html/admin/cli/upgrade.php

# Purge caches
docker compose exec moodle php /var/www/html/admin/cli/purge_caches.php

# View logs
docker compose logs -f moodle

# Reset everything (deletes all data)
docker compose down -v

# Access MariaDB
docker compose exec mariadb mysql -u moodle -p moodle
```

## psaelmsync Plugin Architecture

The plugin handles bidirectional sync between Moodle and ELM:

**Inbound (ELM → Moodle):**
- `lib.php:local_psaelmsync_sync()` - Main sync function called by scheduled task
- Fetches enrollment records from CData API, processes Enrol/Suspend actions
- Creates users if they don't exist (OAuth2 auth, GUID as idnumber)
- Uses SHA256 hash of record fields to deduplicate already-processed records
- Logs to `local_psaelmsync_logs` and `local_psaelmsync_runs` tables

**Outbound (Moodle → ELM):**
- `classes/observer.php` - Listens for `\core\event\course_completed` events
- Only sends completions for courses with `completion_opt_in` custom field enabled
- Posts completion data to CData API

**Scheduled Tasks** (`db/tasks.php`):
- `sync_task` - Runs every 10 min (6AM-6PM) to pull enrollments
- `process_course_completion` - Runs every 5 min

**Key Database Tables:**
- `local_psaelmsync_logs` - Individual enrollment/completion records
- `local_psaelmsync_runs` - Sync run summaries with counts

**Admin Settings** (`settings.php`):
- API URL/token for enrollment sync
- Completion API URL/token for sending completions
- Notification emails for errors
- Date filter (minutes) for API queries

## Moodle Plugin Conventions

- Plugin component: `local_psaelmsync`
- Version file: `version.php` (increment `$plugin->version` for DB upgrades)
- Language strings: `lang/en/local_psaelmsync.php`
- Capabilities: `db/access.php`
- DB schema changes: `db/install.xml` and `db/upgrade.php`
- After any DB changes, run upgrade CLI command

## Environment Details

- Moodle: 4.5 (MOODLE_405_STABLE)
- PHP: 8.1
- Database: MariaDB 10.11
- Moodle URL: http://localhost:8081
- Claude Code CLI is pre-installed in the container
