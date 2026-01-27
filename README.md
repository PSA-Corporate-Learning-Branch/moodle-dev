# PSA Moodle Development Environment

Docker-based Moodle 4.5 development environment for BC Gov PSA.

## Components

| Component | Location | Description |
|-----------|----------|-------------|
| **psaelmsync** | `plugins/psaelmsync/` | Local plugin for ELM enrollment synchronization |
| **bcgovpsa** | `themes/bcgovpsa/` | BC Gov PSA Boost child theme |

Both are mounted as volumes for live development—edit locally, changes reflect immediately.

## Prerequisites

- Docker and Docker Compose
- Production SQL dump: `PROD-mysql-moodle_2025-03-11.sql` (place in project root)

## Quick Start

```bash
git clone <repository-url>
cd moodle-dev
docker compose up -d
```

First run takes 10-15 minutes for the ~900MB database import. Monitor with:
```bash
docker compose logs -f mariadb
```

Access Moodle at **http://localhost:8081**

## Development

### Plugin/Theme Development

Edit files in `plugins/` or `themes/` directories. Changes appear immediately in the container.

After modifying `version.php` or database schema:
```bash
docker compose exec moodle php /var/www/html/admin/cli/upgrade.php
```

Purge caches when needed:
```bash
docker compose exec moodle php /var/www/html/admin/cli/purge_caches.php
```

### Claude Code

Claude Code CLI is pre-installed in the container. First use requires authentication:
```bash
docker compose exec moodle claude
```

Credentials persist across container restarts.

### Container Access

```bash
docker compose exec moodle bash
```

### Database Access

```bash
docker compose exec mariadb mysql -u moodle -pmoodlepassword moodle
```

## Commands Reference

| Action | Command |
|--------|---------|
| Start | `docker compose up -d` |
| Stop | `docker compose down` |
| Logs | `docker compose logs -f moodle` |
| Rebuild | `docker compose build moodle && docker compose up -d` |
| Reset all data | `docker compose down -v` |

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
2. Run `docker compose up -d`
3. Complete installation wizard at http://localhost:8081

## Project Structure

```
moodle-dev/
├── plugins/
│   └── psaelmsync/         # ELM sync plugin (mounted volume)
├── themes/
│   └── bcgovpsa/           # PSA theme (mounted volume)
├── db-init/                # Database initialization scripts
├── docker-compose.yml
├── Dockerfile
├── docker-entrypoint.sh
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
