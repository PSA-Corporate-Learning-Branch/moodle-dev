#!/usr/bin/env python3
"""
Find tables holding UTF-8 bytes in latin1 columns - the tables that need the
binary bridge.

Detection is done with HEX() on the column, not LIKE '%â€™%'. That matters:
searching for the mojibake *characters* requires the client, the connection
charset and the column collation to all agree on what those characters are,
and when they don't you get zero hits on data that is visibly corrupt. We hit
exactly that last time - see reference/conversion-strategy.md. Matching the
raw byte sequence sidesteps the whole question.

    ./detect_mojibake.py            # scan every latin1 table
    ./detect_mojibake.py book forum_posts

Read-only. Safe to run against production.
"""

import sys

from dbconfig import DB_NAME, require_config, run_query

# UTF-8 byte sequences for characters that are common in real content but
# cannot be produced by correctly-stored latin1 text. Finding these bytes
# inside a latin1 column means the column holds UTF-8.
UTF8_SIGNATURES = [
    ("E28099", "' right single quote"),
    ("E28098", "' left single quote"),
    ("E2809C", '" left double quote'),
    ("E2809D", '" right double quote'),
    ("E28093", "- en dash"),
    ("E28094", "- em dash"),
    ("E280A6", "... ellipsis"),
    ("E28692", "-> right arrow"),
    ("C3A9", "e acute"),
    ("C2A0", "non-breaking space"),
    ("C2AE", "registered mark"),
]

TEXT_TYPES = ("varchar", "char", "text", "tinytext", "mediumtext", "longtext")


def latin1_tables():
    result = run_query(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = '{}'
          AND table_collation LIKE 'latin1%'
        ORDER BY table_name
        """.format(DB_NAME),
        raw=True,
    )
    return [line.strip() for line in (result or "").splitlines() if line.strip()]


def text_columns(table):
    """Every text column in the table - not a sample of the first few."""
    result = run_query(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = '{}'
          AND table_name = '{}'
          AND data_type IN ({})
        ORDER BY ordinal_position
        """.format(
            DB_NAME, table, ",".join("'{}'".format(t) for t in TEXT_TYPES)
        ),
        raw=True,
    )
    return [line.strip() for line in (result or "").splitlines() if line.strip()]


def scan_column(table, column):
    """Return {signature_label: row_count} for signatures present in a column."""
    checks = ",".join(
        "SUM(HEX(`{}`) LIKE '%{}%') AS s{}".format(column, sig, i)
        for i, (sig, _) in enumerate(UTF8_SIGNATURES)
    )
    result = run_query(
        "SELECT {} FROM `{}`".format(checks, table), raw=True
    )
    if not result or not result.strip():
        return {}

    counts = result.strip().split("\t")
    hits = {}
    for i, (_, label) in enumerate(UTF8_SIGNATURES):
        if i < len(counts) and counts[i] not in ("NULL", ""):
            n = int(counts[i])
            if n:
                hits[label] = n
    return hits


def main():
    require_config()
    tables = sys.argv[1:] or latin1_tables()

    if not sys.argv[1:]:
        print("Scanning {} latin1 tables in `{}`\n".format(len(tables), DB_NAME))
    affected = []

    for table in tables:
        columns = text_columns(table)
        if not columns:
            continue

        table_hits = {}
        for column in columns:
            hits = scan_column(table, column)
            if hits:
                table_hits[column] = hits

        if table_hits:
            affected.append(table)
            print("{}".format(table))
            for column, hits in table_hits.items():
                summary = ", ".join(
                    "{} x{}".format(label, n) for label, n in sorted(hits.items())
                )
                print("    {:<24} {}".format(column, summary))
            print()

    print("=" * 60)
    print("{} of {} tables need the binary bridge".format(len(affected), len(tables)))
    if affected:
        print("\nWrite this list to a file and feed it to convert.py:")
        print("  ./detect_mojibake.py | grep -E '^[a-z]' > affected_tables.txt")
        print("\nAffected tables:")
        for table in affected:
            print("  {}".format(table))


if __name__ == "__main__":
    main()
