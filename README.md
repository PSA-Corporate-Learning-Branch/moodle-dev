# moodle-dev

Docker-based Moodle 4.5 development environment for PSA with pre-installed plugins.

## Plugins Included

- **psaelmsync** - Local plugin for ELM enrollment synchronization
- **bcgovpsa** - BC Gov PSA Boost child theme

## Prerequisites

- Docker and Docker Compose installed
- The production SQL dump file: `PROD-mysql-moodle_2025-03-11.sql`

## Quick Start

1. Clone this repository:
   ```bash
   git clone <repository-url>
   cd moodle-dev
   ```

2. Place the SQL dump file in the project root:
   ```bash
   # The file should be named exactly:
   PROD-mysql-moodle_2025-03-11.sql
   ```

3. Start the containers:
   ```bash
   docker compose up -d
   ```

4. Wait for the database import to complete. First run will take several minutes due to the large SQL import. Monitor progress with:
   ```bash
   docker compose logs -f mariadb
   ```

5. Access Moodle at: http://localhost:8080

## Configuration

Create a `.env` file to customize settings:

```env
# Database settings
DB_ROOT_PASSWORD=rootpassword
DB_NAME=moodle
DB_USER=moodle
DB_PASSWORD=moodlepassword

# Moodle settings
MOODLE_WWWROOT=http://localhost:8080
```

## Fresh Install (No SQL Import)

To start with a fresh Moodle installation instead of importing the production database:

1. Remove or rename the SQL file
2. Run `docker compose up -d`
3. Visit http://localhost:8080 to complete the installation wizard

## Useful Commands

```bash
# Start containers
docker compose up -d

# Stop containers
docker compose down

# View logs
docker compose logs -f

# View Moodle logs only
docker compose logs -f moodle

# Rebuild Moodle image (after plugin updates)
docker compose build --no-cache moodle

# Reset everything (deletes all data)
docker compose down -v

# Access Moodle container shell
docker compose exec moodle bash

# Access MariaDB CLI
docker compose exec mariadb mysql -u moodle -p moodle

# Run Moodle upgrade
docker compose exec moodle php /var/www/html/admin/cli/upgrade.php

# Purge Moodle caches
docker compose exec moodle php /var/www/html/admin/cli/purge_caches.php
```

## Troubleshooting

### Database import takes too long
The production SQL file is large (~900MB). First startup may take 10-15 minutes. Monitor with `docker compose logs -f mariadb`.

### Moodle shows database connection error
Ensure the MariaDB container is healthy before Moodle starts:
```bash
docker compose ps
```

### Need to re-import the database
```bash
docker compose down -v
docker compose up -d
```

### Plugin not appearing
After rebuilding the image, run Moodle's upgrade:
```bash
docker compose exec moodle php /var/www/html/admin/cli/upgrade.php
```

### Permission errors
If you see permission errors, reset ownership:
```bash
docker compose exec moodle chown -R www-data:www-data /var/www/moodledata
```

## File Structure

```
moodle-dev/
├── docker-compose.yml      # Docker services configuration
├── Dockerfile              # Custom Moodle image with plugins
├── docker-entrypoint.sh    # Container startup script
├── config.php.template     # Moodle config template
├── db-init/                # Database initialization scripts
│   └── 01-import-database.sh
├── .gitignore              # Excludes SQL files and secrets
└── README.md
```

## Technical Details

- **Base Image**: php:8.1-apache
- **Moodle Version**: 4.5 (MOODLE_405_STABLE)
- **Database**: MariaDB 10.11
- **Moodle Port**: 8080
- **MariaDB Port**: 3306
- **Data Persistence**: Docker volumes for database and moodledata

## Notes

- The SQL dump file is excluded from git via `.gitignore`
- The entrypoint script automatically updates wwwroot in the database on startup
- Data persists in Docker volumes between restarts
