# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Podman-based Moodle 4.5 development environment for BC Gov PSA. Custom components are cloned into `plugins/` and `themes/` and volume-mounted into the container for active development:

**Plugins** (all under `plugins/`):
- **psaelmsync** (`local_psaelmsync`) - Syncs enrollment data from ELM and sends completion data back via CData API
- **githubsync** (`local_githubsync`) - GitHub-based course sync plugin
- **pathcurator** (`mod_pathcurator`) - Activity module for curating learning paths
- **course_search** (`block_course_search`) - Block plugin for course search

**Theme:**
- **bcgovpsa** (`themes/bcgovpsa/`) - Boost child theme for BC Gov PSA branding

## Development Commands

```bash
# Start environment
podman compose up -d

# Stop environment
podman compose down

# Rebuild after Containerfile changes
podman compose build moodle && podman compose down && podman compose up -d

# Access container shell
podman compose exec moodle bash

# Run Moodle upgrade (after plugin changes)
podman compose exec moodle php /var/www/html/admin/cli/upgrade.php

# Purge caches
podman compose exec moodle php /var/www/html/admin/cli/purge_caches.php

# View logs
podman compose logs -f moodle

# Reset everything (deletes all data)
podman compose down -v

# Access MariaDB
podman compose exec mariadb mysql -u moodle -p moodle
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
