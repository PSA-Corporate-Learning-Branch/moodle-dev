#!/bin/bash
set -e

echo "Starting Moodle container initialization..."

# Ensure dev user owns their home directory volumes
chown -R dev:dev /home/dev/.claude /home/dev/.local 2>/dev/null || true

# Install Claude Code CLI for dev user if not already installed
if [ ! -f /home/dev/.local/bin/claude ]; then
    echo "Installing Claude Code CLI for dev user..."
    su - dev -c 'curl -fsSL https://claude.ai/install.sh | bash'
    echo "Claude Code installed. Run 'claude' as dev user to authenticate."
else
    echo "Claude Code CLI already installed."
fi

# Ensure claude is in PATH via symlink
if [ -f /home/dev/.local/bin/claude ] && [ ! -f /usr/local/bin/claude ]; then
    ln -sf /home/dev/.local/bin/claude /usr/local/bin/claude
fi

# Give dev user write access to plugin/theme directories
chown -R dev:www-data /var/www/html/local/psaelmsync /var/www/html/theme/bcgovpsa 2>/dev/null || true

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
