# Moodle Database UTF-8 Conversion Strategy

## Executive Summary
Your Moodle database has 481 tables in `latin1_swedish_ci` encoding that need conversion to `utf8mb4_unicode_ci`. The main challenge is that many tables contain UTF-8 data stored incorrectly in latin1 columns, causing mojibake (garbled characters).

## Key Findings

### Mojibake Examples Found
- `â†'` should be `→` (arrow symbol)
- `â€™` should be `'` (smart quote)
- `â€œ` and `â€` should be `"` (double quotes)
- `Â` should be non-breaking space

### Critical Tables with Mojibake
1. **book** - Course book content
2. **book_chapters** - Chapter content
3. **forum_posts** - Forum messages
4. **assignfeedback_comments** - Assignment feedback
5. **quiz_attempts** - Quiz responses
6. **message** - User messages

## Conversion Process

### Step 1: Pre-Conversion Preparation
```bash
# 1. Create full backup
mysqldump --routines --triggers --single-transaction moodle > moodle_pre_conversion_$(date +%Y%m%d).sql

# 2. Create working database copy for testing
mysql -e "CREATE DATABASE moodle_test"
mysql moodle_test < moodle_pre_conversion_*.sql

# 3. Test conversion on copy first
```

### Step 2: Mojibake Detection
```sql
-- Run this query to identify tables with mojibake
SELECT 
    'book' as table_name,
    COUNT(*) as mojibake_count
FROM book
WHERE intro LIKE '%â†%' OR intro LIKE '%â€%' 
   OR name LIKE '%â†%' OR name LIKE '%â€%'
UNION ALL
SELECT 
    'forum_posts' as table_name,
    COUNT(*) as mojibake_count
FROM forum_posts
WHERE message LIKE '%â†%' OR message LIKE '%â€%' 
   OR subject LIKE '%â†%' OR subject LIKE '%â€%';
```

### Step 3: Conversion Method for Mojibake Tables

For tables containing UTF-8 data in latin1 columns, use the **"Binary Bridge Method"**:

```sql
-- Example for 'book' table
-- 1. Backup the table
CREATE TABLE book_backup_20250617 AS SELECT * FROM book;

-- 2. Convert text columns to binary (preserves byte sequences)
ALTER TABLE book 
    MODIFY COLUMN name VARBINARY(255),
    MODIFY COLUMN intro LONGBLOB;

-- 3. Convert binary to UTF-8 (reinterprets bytes correctly)
ALTER TABLE book 
    MODIFY COLUMN name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    MODIFY COLUMN intro LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 4. Convert entire table
ALTER TABLE book CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 5. Verify fix
SELECT id, name FROM book WHERE name LIKE '%→%' LIMIT 5;
```

### Step 4: Direct Conversion for Clean Tables

For system tables without user content:
```sql
-- Direct conversion (safe for tables without text content issues)
ALTER TABLE analytics_indicator_calc CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## Execution Plan

### Phase 1: High-Priority Content Tables (1-2 hours)
Convert tables with user-generated content that likely contain mojibake:
- book, book_chapters
- forum_posts, forum_discussions  
- assignfeedback_comments
- quiz_attempts, quiz_answers
- message, blog_entry
- wiki, glossary_entries

### Phase 2: System Tables (30-60 minutes)
Convert analytics and logging tables:
- analytics_* tables
- log tables
- cache tables
- config tables

### Phase 3: Remaining Tables (1-2 hours)
Convert all other latin1 tables using direct conversion.

## Validation Steps

1. **Character Validation**
```sql
-- Check for successful mojibake fixes
SELECT 
    COUNT(*) as fixed_arrows
FROM book 
WHERE intro LIKE '%→%' OR name LIKE '%→%';

-- Check for remaining mojibake
SELECT 
    COUNT(*) as remaining_issues
FROM book
WHERE intro LIKE '%â†%' OR intro LIKE '%â€%';
```

2. **Table Encoding Validation**
```sql
-- Verify all tables are UTF-8
SELECT 
    table_collation,
    COUNT(*) as table_count
FROM information_schema.tables 
WHERE table_schema = 'moodle'
GROUP BY table_collation;
```

## Rollback Plan

If issues occur:
```sql
-- Example rollback for a single table
DROP TABLE book;
RENAME TABLE book_backup_20250617 TO book;

-- Full database rollback
mysql -e "DROP DATABASE moodle"
mysql -e "CREATE DATABASE moodle"
mysql moodle < moodle_pre_conversion_20250617.sql
```

## Important Warnings

1. **Always test on a copy first** - The mojibake fix is irreversible if done incorrectly
2. **Monitor application logs** - Some cached content may need clearing
3. **Update connection strings** - Ensure application uses `SET NAMES utf8mb4`
4. **Backup retention** - Keep backups for at least 30 days after conversion

## Post-Conversion Tasks

1. Clear Moodle caches
2. Run Moodle database check: `php admin/cli/check_database_schema.php`
3. Test special characters in all major content areas
4. Monitor error logs for encoding issues

## Time Estimate
- Testing: 2-4 hours
- Production conversion: 3-5 hours (depending on database size)
- Validation: 1-2 hours
- Total downtime needed: 4-6 hours