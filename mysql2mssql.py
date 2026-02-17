#!/usr/bin/env python3
"""
mysql2mssql.py - Convert MariaDB/MySQL SQL dump to T-SQL (SQL Server)

Designed for Moodle database dumps. Handles:
  - Data type conversion (MySQL -> T-SQL)
  - Identifier quoting (backticks -> square brackets)
  - AUTO_INCREMENT -> IDENTITY(1,1)
  - Inline KEY/UNIQUE KEY -> CREATE INDEX / CREATE UNIQUE INDEX
  - Backslash escape conversion in INSERT data
  - MySQL-specific syntax removal (ENGINE, LOCK TABLES, conditional comments)
  - SET IDENTITY_INSERT wrappers for INSERT statements
  - Trigger/routine blocks output as comments for manual review

Usage:
    python mysql2mssql.py moodle-prod.sql moodle-tsql.sql
    python mysql2mssql.py moodle-prod.sql --schema-only -o moodle-schema.sql
"""

import sys
import re
import argparse
from pathlib import Path


# ---------------------------------------------------------------------------
# Data-type conversion
# ---------------------------------------------------------------------------

def convert_column_types(line):
    """Convert MySQL column data types to T-SQL equivalents."""

    # Strip unsigned (T-SQL has no unsigned integers)
    line = re.sub(r'\s+unsigned\b', '', line, flags=re.IGNORECASE)

    # Integer types - strip display widths
    line = re.sub(r'\bbigint\(\d+\)',   'bigint',   line, flags=re.IGNORECASE)
    line = re.sub(r'\bmediumint\(\d+\)', 'int',     line, flags=re.IGNORECASE)
    line = re.sub(r'\bint\(\d+\)',      'int',      line, flags=re.IGNORECASE)
    line = re.sub(r'\bsmallint\(\d+\)', 'smallint', line, flags=re.IGNORECASE)
    line = re.sub(r'\btinyint\(\d+\)',  'tinyint',  line, flags=re.IGNORECASE)

    # Text types -> nvarchar (Moodle on SQL Server uses nvarchar)
    line = re.sub(r'\blongtext\b',   'nvarchar(max)', line, flags=re.IGNORECASE)
    line = re.sub(r'\bmediumtext\b', 'nvarchar(max)', line, flags=re.IGNORECASE)
    line = re.sub(r'\btinytext\b',   'nvarchar(255)', line, flags=re.IGNORECASE)
    line = re.sub(r'\btext\b',       'nvarchar(max)', line, flags=re.IGNORECASE)
    line = re.sub(r'\bvarchar\((\d+)\)', r'nvarchar(\1)', line, flags=re.IGNORECASE)

    # Blob types -> varbinary
    line = re.sub(r'\blongblob\b',   'varbinary(max)', line, flags=re.IGNORECASE)
    line = re.sub(r'\bmediumblob\b', 'varbinary(max)', line, flags=re.IGNORECASE)
    line = re.sub(r'\btinyblob\b',   'varbinary(255)', line, flags=re.IGNORECASE)
    line = re.sub(r'\bblob\b',       'varbinary(max)', line, flags=re.IGNORECASE)

    # Float / double
    # MySQL float(M,D) is fixed-precision display -> decimal(M,D) in T-SQL
    line = re.sub(r'\bfloat\((\d+),(\d+)\)', r'decimal(\1,\2)', line, flags=re.IGNORECASE)
    line = re.sub(r'\bdouble\b', 'float', line, flags=re.IGNORECASE)

    # AUTO_INCREMENT -> IDENTITY
    line = re.sub(r'\bAUTO_INCREMENT\b', 'IDENTITY(1,1)', line, flags=re.IGNORECASE)

    # DEFAULT CURRENT_TIMESTAMP
    line = re.sub(r'\bDEFAULT CURRENT_TIMESTAMP\b', 'DEFAULT GETDATE()', line,
                  flags=re.IGNORECASE)

    # Clean up double spaces left by unsigned removal
    line = re.sub(r'  +', ' ', line)

    return line


# ---------------------------------------------------------------------------
# Identifier quoting
# ---------------------------------------------------------------------------

def convert_backticks(text):
    """Replace `identifier` with [identifier]."""
    return re.sub(r'`([^`]*)`', r'[\1]', text)


# ---------------------------------------------------------------------------
# INSERT escape conversion
# ---------------------------------------------------------------------------

def convert_insert_escaping(data):
    """
    Convert MySQL backslash escaping to T-SQL within INSERT VALUES data.

    MySQL uses \\' for literal quotes, \\\\ for backslash, \\n for newline, etc.
    T-SQL uses '' for literal quotes and has no backslash escaping.
    """
    # Fast path: skip expensive parsing if no backslashes
    if '\\' not in data:
        return data

    result = []
    i = 0
    in_string = False
    length = len(data)

    while i < length:
        ch = data[i]

        if in_string:
            if ch == '\\' and i + 1 < length:
                nxt = data[i + 1]
                if nxt == "'":
                    result.append("''")    # escaped quote -> T-SQL ''
                elif nxt == '\\':
                    result.append('\\')    # escaped backslash -> literal \
                elif nxt == 'n':
                    result.append('\n')    # newline
                elif nxt == 'r':
                    result.append('\r')    # carriage return
                elif nxt == 't':
                    result.append('\t')    # tab
                elif nxt == '0':
                    pass                   # null byte -> discard
                else:
                    result.append(nxt)     # unknown escape -> keep char
                i += 2
            elif ch == "'":
                if i + 1 < length and data[i + 1] == "'":
                    result.append("''")    # already-doubled quote
                    i += 2
                else:
                    in_string = False
                    result.append(ch)
                    i += 1
            else:
                result.append(ch)
                i += 1
        else:
            if ch == "'":
                in_string = True
            result.append(ch)
            i += 1

    return ''.join(result)


# ---------------------------------------------------------------------------
# CREATE TABLE processing
# ---------------------------------------------------------------------------

def process_create_table_block(table_name, block_lines):
    """
    Process column/key definitions collected from inside a CREATE TABLE.

    Returns:
        create_lines  - list of strings for the CREATE TABLE statement
        index_lines   - list of strings for CREATE INDEX statements
        has_identity  - whether the table has an IDENTITY column
    """
    columns = []
    primary_key = None
    indexes = []        # [(is_unique, index_name, columns_str), ...]
    has_identity = False

    for raw_line in block_lines:
        stripped = raw_line.strip().rstrip(',')

        # PRIMARY KEY
        if stripped.startswith('PRIMARY KEY'):
            primary_key = stripped
            continue

        # UNIQUE KEY `name` (columns)
        m = re.match(r'UNIQUE KEY\s+`([^`]+)`\s+\((.+)\)', stripped)
        if m:
            indexes.append((True, m.group(1), m.group(2)))
            continue

        # KEY `name` (columns)  -- non-unique index
        m = re.match(r'KEY\s+`([^`]+)`\s+\((.+)\)', stripped)
        if m:
            indexes.append((False, m.group(1), m.group(2)))
            continue

        # Regular column definition
        converted = convert_column_types(raw_line)
        if 'IDENTITY(1,1)' in converted:
            has_identity = True
        columns.append(converted)

    # --- Assemble CREATE TABLE ---
    tsql_table = f'[{table_name}]'
    out = [f'CREATE TABLE {tsql_table} (\n']

    for idx, col in enumerate(columns):
        is_last = (idx == len(columns) - 1) and primary_key is None
        line = col.rstrip('\n').rstrip()

        if is_last:
            line = line.rstrip(',')          # no trailing comma on last item
        elif not line.endswith(','):
            line += ','                      # ensure comma between items

        out.append(convert_backticks(line) + '\n')

    if primary_key:
        # Ensure preceding line has a comma
        prev = out[-1].rstrip('\n').rstrip()
        if not prev.endswith(','):
            out[-1] = prev + ',\n'
        out.append('  ' + convert_backticks(primary_key) + '\n')

    out.append(');\nGO\n\n')

    # --- Assemble CREATE INDEX statements ---
    idx_out = []
    for is_unique, idx_name, idx_cols in indexes:
        u = 'UNIQUE ' if is_unique else ''
        cols = convert_backticks(idx_cols)
        idx_out.append(f'CREATE {u}INDEX [{idx_name}] ON {tsql_table} ({cols});\n')
    if idx_out:
        idx_out.append('GO\n\n')

    return out, idx_out, has_identity


# ---------------------------------------------------------------------------
# Line-level filters
# ---------------------------------------------------------------------------

def is_skip_line(stripped):
    """Return True if the line should be dropped entirely."""
    # MySQL conditional comments  /*!40101 SET ... */;  or  /*!50003 ... */ ;
    if stripped.startswith('/*!') or stripped.startswith('/*M!'):
        # Strip trailing semicolon and whitespace to normalise endings
        tail = stripped.rstrip('; ')
        if tail.endswith('*/'):
            return True
    # LOCK / UNLOCK TABLES
    if stripped.startswith(('LOCK TABLES', 'UNLOCK TABLES')):
        return True
    # SET commands (session variables)
    if stripped.startswith('SET '):
        return True
    # ALTER DATABASE charset
    if stripped.startswith('ALTER DATABASE'):
        return True
    return False


def extract_table_name(line):
    """Extract table name from an INSERT INTO statement."""
    m = re.match(r'INSERT INTO\s+`([^`]+)`', line)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Main conversion
# ---------------------------------------------------------------------------

def convert_file(input_path, out, schema_only=False):
    """Read a MySQL dump and write T-SQL to the output file object."""

    with open(input_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    total = len(lines)
    identity_tables = set()
    stats = {'tables': 0, 'inserts': 0}

    # Preamble
    out.write('-- Converted from MariaDB/MySQL to T-SQL by mysql2mssql.py\n')
    out.write(f'-- Source: {Path(input_path).name}\n')
    out.write('SET NOCOUNT ON;\nGO\n\n')

    i = 0
    while i < total:
        line = lines[i]
        stripped = line.strip()

        # --- Blank lines and SQL comments: pass through ---
        if not stripped or stripped.startswith('--'):
            out.write(line)
            i += 1
            continue

        # --- Skip MySQL-specific lines ---
        if is_skip_line(stripped):
            i += 1
            continue

        # --- DELIMITER blocks (triggers / routines) -> commented out ---
        if stripped.startswith('DELIMITER'):
            if ';;' in stripped:
                out.write('-- ============================================\n')
                out.write('-- NOTE: Trigger/routine block below needs\n')
                out.write('-- manual conversion to T-SQL syntax.\n')
                out.write('-- ============================================\n')
                i += 1
                while i < total and not lines[i].strip().startswith('DELIMITER'):
                    inner = lines[i].strip()
                    if not inner.startswith('/*!'):
                        out.write(f'-- {lines[i].rstrip()}\n')
                    i += 1
                i += 1   # skip closing DELIMITER ;
                out.write('\n')
            else:
                i += 1
            continue

        # --- DROP TABLE IF EXISTS ---
        if stripped.startswith('DROP TABLE IF EXISTS'):
            m = re.match(r'DROP TABLE IF EXISTS\s+`([^`]+)`', stripped)
            if m:
                t = m.group(1)
                out.write(
                    f"IF OBJECT_ID(N'{t}', N'U') IS NOT NULL DROP TABLE [{t}];\nGO\n"
                )
            i += 1
            continue

        # --- CREATE TABLE ---
        if stripped.startswith('CREATE TABLE'):
            m = re.match(r'CREATE TABLE\s+`([^`]+)`', stripped)
            if not m:
                out.write(convert_backticks(line))
                i += 1
                continue

            table_name = m.group(1)
            block = []
            i += 1   # skip the opening CREATE TABLE line

            # Collect column/key definition lines until the closing line
            while i < total:
                inner = lines[i].strip()
                if re.match(r'\)\s*(ENGINE=|;)', inner):
                    break
                block.append(lines[i])
                i += 1
            i += 1   # skip the ) ENGINE=... line

            create_out, index_out, has_identity = process_create_table_block(
                table_name, block
            )
            if has_identity:
                identity_tables.add(table_name)

            for ln in create_out:
                out.write(ln)
            for ln in index_out:
                out.write(ln)

            stats['tables'] += 1
            if stats['tables'] % 100 == 0:
                print(f'  {stats["tables"]} tables converted...', file=sys.stderr)
            continue

        # --- INSERT INTO ---
        if stripped.startswith('INSERT INTO'):
            if schema_only:
                i += 1
                continue

            table_name = extract_table_name(stripped)
            needs_identity = table_name in identity_tables
            tsql_table = f'[{table_name}]'

            if needs_identity:
                out.write(f'SET IDENTITY_INSERT {tsql_table} ON;\n')

            converted = convert_backticks(line)
            converted = convert_insert_escaping(converted)
            out.write(converted)

            if needs_identity:
                out.write(f'SET IDENTITY_INSERT {tsql_table} OFF;\n')

            out.write('GO\n')
            stats['inserts'] += 1
            i += 1
            continue

        # --- Anything else: convert backticks and pass through ---
        out.write(convert_backticks(line))
        i += 1

    # Summary
    print(f'\nConversion complete:', file=sys.stderr)
    print(f'  Tables:              {stats["tables"]}', file=sys.stderr)
    print(f'  INSERT statements:   {stats["inserts"]}', file=sys.stderr)
    print(f'  IDENTITY tables:     {len(identity_tables)}', file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Convert a MariaDB/MySQL SQL dump to T-SQL (SQL Server)'
    )
    parser.add_argument('input', help='Input MySQL/MariaDB SQL dump file')
    parser.add_argument('output', nargs='?',
                        help='Output T-SQL file (default: stdout)')
    parser.add_argument('--schema-only', action='store_true',
                        help='Convert schema only, skip INSERT data')

    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f'Error: {args.input} not found', file=sys.stderr)
        sys.exit(1)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            convert_file(args.input, f, schema_only=args.schema_only)
        print(f'  Output written to:   {args.output}', file=sys.stderr)
    else:
        convert_file(args.input, sys.stdout, schema_only=args.schema_only)


if __name__ == '__main__':
    main()
