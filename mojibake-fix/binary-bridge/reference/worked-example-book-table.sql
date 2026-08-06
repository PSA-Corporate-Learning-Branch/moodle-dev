-- Detailed Example: Converting the 'book' table with mojibake issues
-- This shows the complete process for one table

-- STEP 1: Analyze current state
SELECT 
    'Current Encoding' as check_type,
    table_name,
    table_collation,
    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS 'Size_MB'
FROM information_schema.tables 
WHERE table_schema = 'moodle' 
  AND table_name = 'book';

-- STEP 2: Check for mojibake
SELECT 
    COUNT(*) as total_records,
    COUNT(CASE WHEN intro LIKE '%â†'%' THEN 1 END) as arrow_mojibake,
    COUNT(CASE WHEN intro LIKE '%â€™%' THEN 1 END) as quote_mojibake,
    COUNT(CASE WHEN intro LIKE '%â€œ%' OR intro LIKE '%â€%' THEN 1 END) as doublequote_mojibake,
    COUNT(CASE WHEN name LIKE '%â%' OR intro LIKE '%â%' THEN 1 END) as any_mojibake
FROM book;

-- Show sample mojibake records
SELECT 
    id,
    SUBSTRING(name, 1, 100) as name_sample,
    SUBSTRING(intro, 1, 200) as intro_sample
FROM book
WHERE name LIKE '%â%' OR intro LIKE '%â%'
LIMIT 5;

-- STEP 3: Create backup
CREATE TABLE book_backup_20250617 AS SELECT * FROM book;

-- Verify backup
SELECT COUNT(*) FROM book_backup_20250617;

-- STEP 4: Get column definitions
SELECT 
    column_name,
    data_type,
    character_maximum_length,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'moodle' 
  AND table_name = 'book'
  AND data_type IN ('varchar', 'text', 'longtext', 'mediumtext', 'char');

-- STEP 5: Convert each text column to binary
ALTER TABLE book 
    MODIFY COLUMN name VARBINARY(255),
    MODIFY COLUMN intro LONGBLOB;

-- STEP 6: Convert from binary to UTF-8
ALTER TABLE book 
    MODIFY COLUMN name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
    MODIFY COLUMN intro LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- STEP 7: Convert entire table charset
ALTER TABLE book CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- STEP 8: Verify the conversion worked
-- Check encoding
SELECT 
    table_name,
    table_collation
FROM information_schema.tables 
WHERE table_schema = 'moodle' 
  AND table_name = 'book';

-- Check column encodings
SELECT 
    column_name,
    character_set_name,
    collation_name
FROM information_schema.columns
WHERE table_schema = 'moodle' 
  AND table_name = 'book'
  AND data_type IN ('varchar', 'text', 'longtext', 'mediumtext', 'char');

-- STEP 9: Verify mojibake is fixed
-- Should return 0 for all mojibake patterns
SELECT 
    COUNT(CASE WHEN intro LIKE '%â†'%' THEN 1 END) as remaining_arrow_mojibake,
    COUNT(CASE WHEN intro LIKE '%â€™%' THEN 1 END) as remaining_quote_mojibake,
    COUNT(CASE WHEN intro LIKE '%â€œ%' OR intro LIKE '%â€%' THEN 1 END) as remaining_doublequote_mojibake
FROM book;

-- Should show properly converted characters
SELECT 
    COUNT(CASE WHEN intro LIKE '%→%' THEN 1 END) as fixed_arrows,
    COUNT(CASE WHEN intro LIKE '%'%' THEN 1 END) as fixed_quotes,
    COUNT(CASE WHEN intro LIKE '%"%' THEN 1 END) as fixed_doublequotes
FROM book;

-- Show sample fixed records
SELECT 
    id,
    SUBSTRING(name, 1, 100) as name_fixed,
    SUBSTRING(intro, 1, 200) as intro_fixed
FROM book
WHERE name LIKE '%→%' OR intro LIKE '%→%' 
   OR name LIKE '%'%' OR intro LIKE '%'%'
LIMIT 5;

-- STEP 10: If something went wrong, rollback
-- DROP TABLE book;
-- RENAME TABLE book_backup_20250617 TO book;

-- STEP 11: Once verified, you can drop the backup (after keeping it for safety period)
-- DROP TABLE book_backup_20250617;