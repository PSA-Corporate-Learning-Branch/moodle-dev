#!/bin/bash
# This script imports the Moodle database dump if it exists
# It runs as part of MariaDB's initialization on first boot

SQL_FILE="/sql-import/moodle-import.sql"

if [ -f "$SQL_FILE" ]; then
    echo "=========================================="
    echo "Found SQL import file. Importing database..."
    echo "This may take several minutes for large databases..."
    echo "=========================================="

    # Import the SQL file into the moodle database
    mysql -u root -p"${MARIADB_ROOT_PASSWORD}" "${MARIADB_DATABASE}" < "$SQL_FILE"

    if [ $? -eq 0 ]; then
        echo "=========================================="
        echo "Database import completed successfully!"
        echo "=========================================="
    else
        echo "=========================================="
        echo "Database import failed!"
        echo "=========================================="
        exit 1
    fi
else
    echo "No SQL import file found at $SQL_FILE"
    echo "Moodle will start with an empty database."
fi
