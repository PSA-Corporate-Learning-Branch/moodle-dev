#!/bin/bash
set -e

echo "Starting Moodle container initialization..."

# Generate config.php from template if it doesn't exist
if [ ! -f /var/www/html/config.php ]; then
    echo "Generating config.php from template..."

    cp /var/www/html/config.php.template /var/www/html/config.php

    # Replace placeholders with environment variables
    sed -i "s|{{DB_HOST}}|${DB_HOST:-mariadb}|g" /var/www/html/config.php
    sed -i "s|{{DB_PORT}}|${DB_PORT:-3306}|g" /var/www/html/config.php
    sed -i "s|{{DB_NAME}}|${DB_NAME:-moodle}|g" /var/www/html/config.php
    sed -i "s|{{DB_USER}}|${DB_USER:-moodle}|g" /var/www/html/config.php
    sed -i "s|{{DB_PASSWORD}}|${DB_PASSWORD:-moodlepassword}|g" /var/www/html/config.php
    sed -i "s|{{MOODLE_WWWROOT}}|${MOODLE_WWWROOT:-http://localhost:8081}|g" /var/www/html/config.php
    sed -i "s|{{MOODLE_DATAROOT}}|${MOODLE_DATAROOT:-/var/www/moodledata}|g" /var/www/html/config.php

    chown www-data:www-data /var/www/html/config.php
    echo "config.php generated successfully!"
fi

# Ensure moodledata directory exists and has correct permissions
mkdir -p ${MOODLE_DATAROOT:-/var/www/moodledata}
chown -R www-data:www-data ${MOODLE_DATAROOT:-/var/www/moodledata}
chmod 755 ${MOODLE_DATAROOT:-/var/www/moodledata}

echo "Moodle initialization complete!"
echo "Starting Apache..."

# Execute the main command (apache2-foreground)
exec "$@"
