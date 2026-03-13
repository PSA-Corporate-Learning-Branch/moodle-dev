# MBZ Completion Audit Tool

A command-line tool that analyzes Moodle backup (`.mbz`) files to extract, report on, and compare course completion requirements.

## Why this exists

Moodle's completion configuration is spread across multiple layers — course-level criteria, activity-level tracking, grade requirements, and aggregation rules — making it difficult to get a clear picture of what a student actually needs to do to complete a course. This is especially problematic when:

- You need to verify completion requirements are configured correctly before going live
- Course changes have been made and you need to understand what shifted
- Completion data isn't flowing to external systems (like ELM) and you need to diagnose why
- You're auditing courses across environments without admin access to each one

This tool reads the raw XML inside MBZ backup files and produces a plain-English report of the full completion picture.

## Requirements

- Python 3.8+
- No external dependencies (uses only the standard library)

## Usage

### Analyze a single backup

```bash
python3 mbz_completion_audit.py backup.mbz
```

Produces a full report covering:

- Whether completion tracking is enabled at the course level
- Course completion criteria (the rules that determine when a student has "completed" the course)
- How criteria aggregate (all required vs. any one is sufficient)
- Every activity with completion tracking, grouped by section, with its specific conditions
- Warnings about potential issues

### Compare two backups

```bash
python3 mbz_completion_audit.py old-backup.mbz new-backup.mbz
```

Pass the **older** backup first and the **newer** backup second. The tool produces individual reports for each, followed by a comparison that shows:

- Changes to course-level completion settings
- Course criteria added or removed
- Activities added or removed (flagging which had completion tracking)
- Completion settings changed on activities that exist in both
- Section visibility changes
- An impact assessment highlighting critical issues

## Understanding the output

### Report sections

**Course info** — Basic metadata including whether completion is enabled and whether the ELM completion opt-in custom field is set.

**Course completion criteria** — These are the top-level rules that determine when Moodle marks a student as having completed the course. Common types:

| Criteria Type | Meaning |
|---|---|
| Activity completion | Student must complete specific activity/activities |
| Self completion | Student manually marks themselves complete |
| Date | Completion after a specific date |
| Grade | Student must achieve a minimum course grade |
| Enrolment duration | Student must be enrolled for a minimum period |
| Course completion | Student must complete another course first |

The **aggregation method** determines how multiple criteria combine:
- **All** = every criterion must be met
- **Any** = meeting any single criterion is sufficient

**Activities with completion tracking** — Each activity that has tracking enabled, showing:
- **Tracking type**: Manual (student clicks a checkbox) or Automatic (Moodle checks conditions)
- **Conditions**: What the student must do — view the activity, achieve a passing grade, submit work, reach a SCORM status, etc.
- **\*COURSE CRITERIA\*** tag: This activity is one of the course-level completion requirements

**Summary** — Counts and warnings, including:
- Hidden activities/sections that have completion tracking (students can't see or access these)
- Completion enabled with no criteria defined (students can never complete)
- Criteria referencing missing or hidden activities

### Comparison sections

**Course completion criteria changes** — Criteria added to or removed from the course-level requirements.

**Activities removed/added** — Grouped by whether they had completion tracking. Activities that were course criteria are flagged with `**WAS COURSE CRITERIA**`.

**Completion settings changed** — Activities present in both backups where tracking, visibility, conditions, or section placement changed.

**Impact assessment** — Plain-language analysis of what the changes mean operationally, including warnings about broken completion paths and ELM integration effects.

## Moodle completion concepts

For reference, here's how Moodle's completion system is structured (and what this tool reads from the MBZ):

### Two levels of completion

1. **Activity completion** — Per-activity tracking. Configured in each activity's settings. Determines whether a green checkmark appears next to the activity. This is stored in `activities/*/module.xml` in the backup.

2. **Course completion** — Course-level rules that determine when Moodle considers the student to have finished the course. This typically references activity completions ("student must complete quiz X") but can also use grades, dates, or other criteria. Stored in `completion.xml`.

A common source of confusion: **activity completion tracking does not automatically feed into course completion.** Activities must be explicitly added as course completion criteria for them to count. A course can have 50 activities with green checkmarks and still show the student as "not completed" if none of those activities are listed in the course completion criteria.

### Where the data lives in an MBZ

| File | What it contains |
|---|---|
| `course/course.xml` | `enablecompletion`, `showcompletionconditions`, custom fields |
| `completion.xml` | Course completion criteria and aggregation methods |
| `activities/*/module.xml` | Per-activity tracking mode, view/grade conditions |
| `activities/*/<type>.xml` | Type-specific rules (SCORM status, quiz attempts, forum posts) |
| `activities/*/grades.xml` | Pass grade and max grade for graded activities |
| `sections/*/section.xml` | Section names, visibility, activity ordering |

### PSA-specific: ELM opt-in

The `completion_opt_in` custom field controls whether the `psaelmsync` plugin sends completion data to ELM when a student completes the course. This tool reads and reports on this field. If opt-in is enabled but no course completion criteria exist, completions will never be sent because no student can reach "completed" status.

## Examples

### Single backup — healthy course

```
COURSE COMPLETION CRITERIA
------------------------------------------------------------
  Overall aggregation: All criteria must be met

  - [Activity completion] Final Assessment
  - [Activity completion] Module 1 Quiz
  - [Activity completion] Module 2 Quiz
    -> Activity completion aggregation: All of 3 must be met
```

This course requires students to complete all three quizzes.

### Comparison — criteria removed

```
IMPACT ASSESSMENT
----------------------------------------------------------------------
  CRITICAL: All course completion criteria have been removed.
  - Students can no longer complete this course through any criteria path.
  - Existing completions are preserved, but new completions cannot occur.
```

### Comparison — tracking added to activities

```
COMPLETION SETTINGS CHANGED ON EXISTING ACTIVITIES:
  [book] 1. You and HR
    - tracking: None -> Automatic (conditions)
    - view required: False -> True
```

This activity now shows a checkmark when the student views it, but unless it's also added as a course completion criterion, it doesn't affect course completion.

## Limitations

- Only reads completion configuration, not student completion records (those are in user data backups)
- Does not evaluate restrict access conditions (availability rules that hide activities based on other completions)
- Quiz question counts and content are not analyzed — only grade thresholds
- SCORM internal completion logic (SCO-level tracking) is not parsed beyond the top-level status requirement
- The tool reads whatever is in the MBZ; if the backup was taken with certain settings excluded, those won't appear
