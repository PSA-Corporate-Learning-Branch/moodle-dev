# The Binary Bridge Method

Converting Moodle tables where **UTF-8 bytes were stored in latin1 columns**, without
destroying the text. This is the method that worked in June 2025 (33 tables, log in
`reference/2025-06-17-successful-run.log`).

---

## The one-sentence version

The bytes in your database were always correct — only the *label* on the column was
wrong. The binary bridge changes the label without touching the bytes, by routing
through a binary type that has no label at all.

Everything below is elaboration on that sentence.

---

## Why the data broke

A MySQL text column is two separate things:

1. **The bytes on disk**
2. **A charset label** declaring how to interpret those bytes

Moodle sent correct UTF-8. The columns were declared `latin1`. Because the connection
was also latin1, MySQL did no conversion — it stored the UTF-8 bytes verbatim into a
column labelled latin1.

So a right single quote `'` sat on disk as its correct UTF-8 bytes `E2 80 99`, in a
column insisting those were three separate latin1 characters.

Nothing was corrupt yet. It rendered fine for years, because the bytes went out the
same way they came in.

**The corruption happens at the moment something believes the label.** Convert
latin1 → UTF-8 and MySQL faithfully does this:

| byte | read as latin1/cp1252 | re-encoded to UTF-8 |
|------|----------------------|---------------------|
| `E2` | `â`                  | `C3 A2`             |
| `80` | `€`                  | `E2 82 AC`          |
| `99` | `™`                  | `E2 84 A2`          |

Three bytes become nine, and `'` becomes `â€™`. That is your mojibake — and it is now
*genuinely, correctly encoded* mojibake. The error moved out of the label and into the
data itself.

Same mechanism produced the other patterns in the old notes:

| real character | 1 pass | 2 passes |
|----------------|--------|----------|
| `'` | `â€™` | `Ã¢â‚¬â„¢` |
| `→` | `â†’` | `Ã¢â€ â€™` |
| `é` | `Ã©`  | `ÃƒÂ©` |

Both depths appear in this database — the `charset/` scripts were chasing the 2-pass
patterns, which is a strong hint some content was run through a bad conversion twice.

---

## Why the obvious fix is the worst thing you can do

```sql
ALTER TABLE book CONVERT TO CHARACTER SET utf8mb4;   -- DO NOT
```

This means: *"these bytes are latin1, please re-encode them as utf8mb4."* MySQL trusts
the label and performs exactly the table above, permanently. You bake the mojibake into
the stored bytes and lose the clean original.

This is the trap your colleague identified in 2025, and it's why the naive 500-query
migration was the wrong move.

---

## The bridge

MySQL offers no "just relabel this column" operation — any charset change on a text
column triggers transcoding. But **binary types (`BLOB`, `VARBINARY`) have no charset at
all**, and that's the loophole.

```sql
-- leg 1: text -> binary.  No target charset exists, so nothing to convert *to*.
ALTER TABLE book MODIFY COLUMN intro LONGBLOB;

-- leg 2: binary -> text.  No source charset exists, so nothing to convert *from*.
ALTER TABLE book MODIFY COLUMN intro LONGTEXT
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Trace the bytes:

```
start    E2 80 99   labelled latin1     renders as  â€™
leg 1    E2 80 99   labelled <none>     (bytes copied verbatim)
leg 2    E2 80 99   labelled utf8mb4    renders as  '
```

**The bytes never change. Only the label does.** Each leg is byte-preserving because
each is missing one half of the pair MySQL needs to justify a conversion. Binary is the
neutral middle ground — the *bridge* — and going `latin1 → binary → utf8mb4` sidesteps
the transcode that `latin1 → utf8mb4` forces on you.

The apostrophe now renders correctly because it was a correct apostrophe the whole time.
You didn't repair the text; you stopped MySQL from lying about it.

A third statement follows, to fix the table's *default* charset for anything not handled
column-by-column. By then the text columns are already utf8mb4, so it's a no-op for them:

```sql
ALTER TABLE book CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

---

## The precondition that makes it dangerous

**The binary bridge is only correct for columns that actually contain UTF-8 bytes.**

If a latin1 column holds *genuine* latin1 — a real `é` stored as the single byte `E9` —
the bridge relabels `E9` as UTF-8. But `E9` alone is not valid UTF-8 (it's a lead byte
promising two continuation bytes that aren't there). You get replacement characters,
invalid sequences, or truncation.

Those columns need the ordinary `CONVERT TO CHARACTER SET`, which transcodes properly.

So the two methods are not competing options — **they apply to different tables**, and
you must find out which is which first. That's the entire job of `detect_mojibake.py`.
In 2025 the split was 33 tables needing the bridge, 448 safe for direct conversion.

---

## Detection: use HEX(), not LIKE

The 2025 attempt burned time on this. Searching for the mojibake *characters*:

```sql
SELECT COUNT(*) FROM book WHERE intro LIKE '%â€™%';   -- returns 0 on corrupt data
```

...requires your literal to survive your editor, the mysql client, the connection
charset, *and* comparison against the column's collation. Any mismatch in that chain
compares the wrong bytes, returns zero rows, and tells you the data is clean when it
isn't. That produced a full round of false negatives last time.

Match the **bytes** instead:

```sql
SELECT COUNT(*) FROM book WHERE HEX(intro) LIKE '%E28099%';
```

`HEX()` renders the column as ASCII hex digits, so the comparison involves no charset
interpretation anywhere. This is what finally located the 178 affected forum posts.

The detector looks for byte sequences that are common in real content but **cannot be
produced by correctly-stored latin1** — smart quotes, dashes, ellipsis, arrows, `é`,
non-breaking space. Their presence in a latin1 column is proof the column holds UTF-8.

---

## Running it

```bash
export MOODLE_DB_NAME=moodle_convert
export MOODLE_DB_USER=mooconvert
export MOODLE_DB_PASS='...'          # passed via MYSQL_PWD, not visible in ps

# 1. find the affected tables (read-only, safe on production)
./detect_mojibake.py

# 2. review the DDL before anything runs
./convert.py --sql book forum_posts

# 3. save the list, generate the full script
./detect_mojibake.py | grep -E '^[a-z]' > affected_tables.txt
./convert.py --sql --from-file affected_tables.txt > convert.sql

# 4. execute (per-table backup created automatically)
./convert.py --execute --from-file affected_tables.txt

# 5. confirm — expect zero hits
./detect_mojibake.py book forum_posts
```

Rollback for any table:

```sql
DROP TABLE `book`;
RENAME TABLE `book_backup_20250805_120000` TO `book`;
```

---

## Gotchas

**Test on a restored copy first.** Getting this wrong is destructive and the mojibake
form is painful to reverse. Non-negotiable given this is a backup-restoration response.

**Index key length.** utf8mb4 is 4 bytes per character, so an indexed `varchar(255)`
needs 1020 bytes. InnoDB's older `COMPACT`/`REDUNDANT` row formats cap index prefixes at
767 and will fail with *"Specified key was too long"*. Moodle has many indexed
`varchar(255)` columns. Use `DYNAMIC` or `COMPRESSED` row format.

**Double-encoded content.** Data that went through a bad conversion twice needs the
bridge applied twice. Re-run `detect_mojibake.py` after converting — if byte signatures
are still present, the data was corrupted at a greater depth. Don't assume one pass is
enough.

**Don't mix methods within a table.** Bridge *all* text columns in a table or none.

**Afterwards:** purge Moodle caches, ensure the app connects with `SET NAMES utf8mb4`,
and run `php admin/cli/check_database_schema.php`. Leaving the connection charset at
latin1 recreates the original problem on every new write.

---

## Files

| | |
|---|---|
| `detect_mojibake.py` | Byte-signature scan. Read-only. Run first. |
| `convert.py` | The conversion. `--sql` to review, `--execute` to run. |
| `dbconfig.py` | Connection settings from environment variables. |
| `reference/worked-example-book-table.sql` | The method by hand on one table, with verification queries. |
| `reference/conversion-strategy.md` | Original 2025 phasing, rollback and validation plan. |
| `reference/2025-06-17-successful-run.log` | The run that worked — 33 tables bridged, 448 direct. |
| `reference/high_priority_tables.txt` | Content tables that had mojibake in 2025. |
| `reference/system_tables.txt` | Tables that were safe for direct conversion. |

The 2025 table lists are a **starting hypothesis, not an answer** — re-run detection
against the restored database rather than trusting them.

---

## Changes from the 2025 scripts

Two fixes carried into `convert.py`:

- **`NOT NULL` is now preserved.** `MODIFY COLUMN` replaces the whole column
  definition, and the old script omitted the constraint on leg 2 — silently making
  columns nullable and drifting the schema from what Moodle expects.
  `check_database_schema.php` would flag these.
- **All text columns are scanned**, not just the first two. The old detector sampled
  `columns[:2]` for speed and could miss mojibake in later columns.

Credentials now come from the environment. They were hardcoded in the original scripts,
which is why those are not in this repo; if that password is still valid anywhere, rotate
it.
