#!/usr/bin/env python3
"""
Binary bridge conversion: latin1 columns holding UTF-8 bytes -> real utf8mb4.

    ./convert.py --sql book forum_posts        # print the DDL, change nothing
    ./convert.py --sql --from-file affected_tables.txt > convert.sql
    ./convert.py --execute book                # run it, with a per-table backup

Always run --sql first and read what it is about to do.

For each text column this emits two ALTERs:

    ALTER TABLE book MODIFY COLUMN intro LONGBLOB;                  -- leg 1
    ALTER TABLE book MODIFY COLUMN intro LONGTEXT                   -- leg 2
        CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

Leg 1 strips the charset label without touching the bytes. Leg 2 reattaches a
correct label. See README.md for why that is the whole trick.

Only run this against tables that detect_mojibake.py flags. A latin1 column
that genuinely holds latin1 text will be corrupted by this - it needs a plain
CONVERT TO CHARACTER SET instead.
"""

import argparse
import datetime
import sys

from dbconfig import DB_NAME, require_config, run_query

TARGET_CHARSET = "utf8mb4"
TARGET_COLLATION = "utf8mb4_unicode_ci"

# text type -> the binary type of matching maximum length
BINARY_EQUIVALENT = {
    "varchar": "VARBINARY({length})",
    "char": "BINARY({length})",
    "tinytext": "TINYBLOB",
    "text": "BLOB",
    "mediumtext": "MEDIUMBLOB",
    "longtext": "LONGBLOB",
}


def text_column_defs(table):
    """
    Full definition of every text column, so leg 2 can put back exactly what
    leg 1 took away.

    column_type is used verbatim ('varchar(255)', 'longtext') rather than
    rebuilt from data_type + length, which is how the original script lost
    display widths on a few columns.
    """
    result = run_query(
        """
        SELECT column_name, data_type, column_type, character_maximum_length,
               is_nullable, column_default, column_comment
        FROM information_schema.columns
        WHERE table_schema = '{}'
          AND table_name = '{}'
          AND data_type IN ('varchar','char','tinytext','text','mediumtext','longtext')
        ORDER BY ordinal_position
        """.format(DB_NAME, table),
        raw=True,
    )
    if not result:
        return []

    columns = []
    for line in result.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        columns.append(
            {
                "name": parts[0],
                "data_type": parts[1],
                "column_type": parts[2],
                "length": parts[3],
                "nullable": parts[4] == "YES",
                # mysql -N prints SQL NULL as the literal string NULL
                "default": None if parts[5] == "NULL" else parts[5],
                "comment": parts[6],
            }
        )
    return columns


def binary_type(col):
    template = BINARY_EQUIVALENT[col["data_type"]]
    return template.format(length=col["length"])


def column_suffix(col):
    """
    NOT NULL / DEFAULT / COMMENT clauses.

    MODIFY COLUMN replaces the entire definition, so anything omitted here is
    silently dropped. The 2025 script omitted NOT NULL, which quietly made a
    number of columns nullable and drifted the schema away from what Moodle
    expects - check_database_schema.php will flag those.
    """
    parts = []
    parts.append("NULL" if col["nullable"] else "NOT NULL")

    if col["default"] is not None:
        escaped = col["default"].replace("\\", "\\\\").replace("'", "\\'")
        parts.append("DEFAULT '{}'".format(escaped))
    elif col["nullable"]:
        parts.append("DEFAULT NULL")

    if col["comment"]:
        escaped = col["comment"].replace("\\", "\\\\").replace("'", "\\'")
        parts.append("COMMENT '{}'".format(escaped))

    return " ".join(parts)


def table_ddl(table, backup_suffix):
    """The full statement list for one table, in execution order."""
    columns = text_column_defs(table)
    if not columns:
        return [], []

    backup = "{}_backup_{}".format(table, backup_suffix)
    statements = [
        "-- {} ({} text columns)".format(table, len(columns)),
        "CREATE TABLE `{}` AS SELECT * FROM `{}`;".format(backup, table),
    ]

    statements.append("-- leg 1: drop the charset label, keep the bytes")
    for col in columns:
        statements.append(
            "ALTER TABLE `{}` MODIFY COLUMN `{}` {};".format(
                table, col["name"], binary_type(col)
            )
        )

    statements.append("-- leg 2: reattach a correct charset label")
    for col in columns:
        statements.append(
            "ALTER TABLE `{}` MODIFY COLUMN `{}` {} CHARACTER SET {} COLLATE {} {};".format(
                table,
                col["name"],
                col["column_type"].upper(),
                TARGET_CHARSET,
                TARGET_COLLATION,
                column_suffix(col),
            )
        )

    statements.append("-- table default, for any column types not covered above")
    statements.append(
        "ALTER TABLE `{}` CONVERT TO CHARACTER SET {} COLLATE {};".format(
            table, TARGET_CHARSET, TARGET_COLLATION
        )
    )
    statements.append("")

    return statements, backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tables", nargs="*", help="tables to convert")
    parser.add_argument("--from-file", help="file with one table name per line")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sql", action="store_true", help="print DDL, change nothing")
    group.add_argument("--execute", action="store_true", help="run the conversion")
    args = parser.parse_args()

    require_config()

    tables = list(args.tables)
    if args.from_file:
        with open(args.from_file) as f:
            tables.extend(
                line.strip()
                for line in f
                if line.strip() and not line.startswith("#")
            )
    if not tables:
        sys.exit("No tables given. Pass names or use --from-file.")

    suffix = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.sql:
        print("-- Binary bridge conversion for `{}`".format(DB_NAME))
        print("-- Generated {}".format(datetime.datetime.now().isoformat(" ")))
        print("-- Review before running. Rollback for each table is:")
        print("--   DROP TABLE `<table>`; RENAME TABLE `<backup>` TO `<table>`;")
        print()
        for table in tables:
            statements, _ = table_ddl(table, suffix)
            if not statements:
                print("-- {}: no text columns, skipped\n".format(table))
                continue
            print("\n".join(statements))
        return

    print("Converting {} table(s) in `{}`".format(len(tables), DB_NAME))
    print("Backups will be suffixed _backup_{}\n".format(suffix))
    if input("Proceed? (yes/no): ").strip().lower() != "yes":
        sys.exit("Cancelled.")

    converted, failed = [], []
    for table in tables:
        statements, backup = table_ddl(table, suffix)
        if not statements:
            print("  {}: no text columns, skipped".format(table))
            continue

        print("  {} -> backup {}".format(table, backup))
        ok = True
        for statement in statements:
            if statement.startswith("--") or not statement.strip():
                continue
            if run_query(statement) is None:
                print("    FAILED: {}".format(statement[:120]))
                ok = False
                break

        if ok:
            converted.append(table)
            print("    done")
        else:
            failed.append((table, backup))
            print("    left partially converted - restore from {}".format(backup))

    print("\n{} converted, {} failed".format(len(converted), len(failed)))
    for table, backup in failed:
        print("  DROP TABLE `{}`; RENAME TABLE `{}` TO `{}`;".format(table, backup, table))
    if converted:
        print("\nVerify with:  ./detect_mojibake.py {}".format(" ".join(converted)))
        print("Expect zero hits. Then clear Moodle caches and run:")
        print("  php admin/cli/check_database_schema.php")


if __name__ == "__main__":
    main()
