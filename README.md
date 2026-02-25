# PSA Moodle Development Environment

Podman-based Moodle 4.5 development environment for BC Gov PSA.

## Components

| Component | Location | Type | Description |
|-----------|----------|------|-------------|
| **psaelmsync** | `plugins/psaelmsync/` | `local_psaelmsync` | ELM enrollment synchronization |
| **githubsync** | `plugins/githubsync/` | `local_githubsync` | GitHub-based course sync |
| **pathcurator** | `plugins/pathcurator/` | `mod_pathcurator` | Learning path curation activity |
| **course_search** | `plugins/course_search/` | `block_course_search` | Course search block |
| **bcgovpsa** | `themes/bcgovpsa/` | theme | BC Gov PSA Boost child theme |

All are mounted as volumes for live development—edit locally, changes reflect immediately.

## Prerequisites

- Podman and Podman Compose
- Production SQL dump: `PROD-mysql-moodle_2025-03-11.sql` (place in project root)

## Quick Start

```bash
git clone <repository-url>
cd moodle-dev
podman compose up -d
```

First run takes 10-15 minutes for the ~900MB database import. Monitor with:
```bash
podman compose logs -f mariadb
```

Access Moodle at **http://localhost:8081**

## Development

### Plugin/Theme Development

Edit files in `plugins/` or `themes/` directories. Changes appear immediately in the container.

After modifying `version.php` or database schema:
```bash
podman compose exec moodle php /var/www/html/admin/cli/upgrade.php
```

Purge caches when needed:
```bash
podman compose exec moodle php /var/www/html/admin/cli/purge_caches.php
```

### Claude Code

Claude Code CLI is pre-installed in the container. First use requires authentication:
```bash
podman compose exec moodle claude
```

Credentials persist across container restarts.

### Container Access

```bash
podman compose exec moodle bash
```

### Database Access

```bash
podman compose exec mariadb mysql -u moodle -pmoodlepassword moodle
```

## Commands Reference

| Action | Command |
|--------|---------|
| Start | `podman compose up -d` |
| Stop | `podman compose down` |
| Logs | `podman compose logs -f moodle` |
| Rebuild | `podman compose build moodle && podman compose up -d` |
| Reset all data | `podman compose down -v` |

## Configuration

Optional `.env` file:

```env
DB_ROOT_PASSWORD=rootpassword
DB_NAME=moodle
DB_USER=moodle
DB_PASSWORD=moodlepassword
MOODLE_WWWROOT=http://localhost:8081
```

## Fresh Install

To start without the production database:

1. Remove or rename `PROD-mysql-moodle_2025-03-11.sql`
2. Run `podman compose up -d`
3. Complete installation wizard at http://localhost:8081

## Project Structure

```
moodle-dev/
├── plugins/
│   ├── psaelmsync/            # ELM sync plugin (mounted volume)
│   ├── githubsync/            # GitHub course sync (mounted volume)
│   ├── pathcurator/           # Learning path activity (mounted volume)
│   └── course_search/         # Course search block (mounted volume)
├── themes/
│   └── bcgovpsa/              # PSA theme (mounted volume)
├── db-init/                   # Database initialization scripts
├── compose.yml
├── Containerfile
├── entrypoint.sh
└── config.php.template
```

## Technical Details

| Component | Version |
|-----------|---------|
| Moodle | 4.5 (MOODLE_405_STABLE) |
| PHP | 8.1 |
| MariaDB | 10.11 |
| Base Image | php:8.1-apache |

**Ports:** Moodle 8081, MariaDB 3306

**Volumes:** Database, moodledata, and Claude Code config persist between restarts.
