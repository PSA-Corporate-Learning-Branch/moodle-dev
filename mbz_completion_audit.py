#!/usr/bin/env python3
"""
Moodle MBZ Completion Audit Tool

Analyzes Moodle backup (.mbz) files to extract and report on completion
requirements. Can compare two backups to identify changes over time.

Usage:
    # Analyze a single backup
    python3 mbz_completion_audit.py backup-new.mbz

    # Compare two backups (older first, newer second)
    python3 mbz_completion_audit.py backup-old.mbz backup-new.mbz
"""

import sys
import os
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


# Moodle completion constants
COMPLETION_TRACKING = {
    0: "None",
    1: "Manual (student marks)",
    2: "Automatic (conditions)",
}

COMPLETION_CRITERIA_TYPES = {
    1: "Self completion",
    2: "Date",
    4: "Activity completion",
    5: "Enrolment duration",
    6: "Grade",
    7: "Role",
    8: "Unenrolment",
    9: "Course completion (other course)",
}

COMPLETION_AGGREGATION = {
    0: "All",
    1: "Any",
}

GRADE_METHODS = {
    1: "Highest grade",
    2: "Average grade",
    3: "First attempt",
    4: "Last attempt",
}


@dataclass
class ActivityCompletion:
    """Completion settings for a single activity."""
    module_id: int
    activity_type: str
    name: str
    section_number: int
    section_name: str = ""
    visible: bool = True
    completion: int = 0  # 0=none, 1=manual, 2=auto
    completionview: bool = False
    completionpassgrade: bool = False
    completiongradeitemnumber: str = ""
    completionexpected: int = 0
    # Activity-type-specific completion rules
    extra_rules: dict = field(default_factory=dict)
    # Grade info (from grades.xml in the activity)
    gradepass: str = ""
    grademax: str = ""


@dataclass
class CourseCriteria:
    """A single course-level completion criterion."""
    criteria_id: int
    criteriatype: int
    criteriatype_name: str
    module: str = ""
    moduleinstance: int = 0
    activity_name: str = ""
    gradepass: str = ""
    enrolperiod: str = ""
    timeend: str = ""


@dataclass
class CourseCompletionConfig:
    """Full completion configuration for a course."""
    course_id: str = ""
    course_shortname: str = ""
    course_fullname: str = ""
    completion_enabled: bool = False
    show_completion_conditions: bool = False
    completion_opt_in: bool = False
    backup_date: str = ""
    # Aggregation methods by criteria type
    aggregation: dict = field(default_factory=dict)
    # Course-level completion criteria
    criteria: list = field(default_factory=list)
    # Per-activity completion settings
    activities: list = field(default_factory=list)
    # Sections
    sections: dict = field(default_factory=dict)
    # Activities removed (for comparison)
    all_activity_ids: set = field(default_factory=set)


def parse_null(value):
    """Convert Moodle's $@NULL@$ to None."""
    if value is None or value == "$@NULL@$" or value == "":
        return None
    return value


def extract_mbz(mbz_path):
    """Extract MBZ to a temp directory and return the path."""
    tmpdir = tempfile.mkdtemp(prefix="mbz_audit_")
    with tarfile.open(mbz_path, "r:gz") as tar:
        tar.extractall(tmpdir, filter="data")
    return tmpdir


def parse_backup_date(tmpdir):
    """Try to get the backup date from moodle_backup.xml."""
    moodle_backup = os.path.join(tmpdir, "moodle_backup.xml")
    if os.path.exists(moodle_backup):
        tree = ET.parse(moodle_backup)
        root = tree.getroot()
        detail = root.find(".//detail")
        backup_date_el = root.find(".//original_course_startdate")
        # Try to get the backup date from the information section
        info = root.find(".//information")
        if info is not None:
            bd = info.find("backup_date")
            if bd is not None and bd.text:
                ts = int(bd.text)
                return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    # Fall back to filename parsing
    return "Unknown"


def parse_sections(tmpdir):
    """Parse all section.xml files and return a dict of section_id -> (number, name, sequence, visible)."""
    sections = {}
    sections_dir = os.path.join(tmpdir, "sections")
    if not os.path.isdir(sections_dir):
        return sections
    for secdir in os.listdir(sections_dir):
        secxml = os.path.join(sections_dir, secdir, "section.xml")
        if not os.path.exists(secxml):
            continue
        tree = ET.parse(secxml)
        root = tree.getroot()
        sec_id = root.get("id")
        number = int(root.findtext("number", "0"))
        name = root.findtext("name", "")
        sequence = root.findtext("sequence", "")
        visible = root.findtext("visible", "1") == "1"
        activity_ids = [int(x) for x in sequence.split(",") if x.strip()]
        sections[number] = {
            "id": sec_id,
            "name": name,
            "visible": visible,
            "activity_ids": activity_ids,
        }
    return sections


def parse_activity_completion(activity_dir, sections_lookup):
    """Parse module.xml and type-specific XML for an activity's completion settings."""
    modxml = os.path.join(activity_dir, "module.xml")
    if not os.path.exists(modxml):
        return None

    tree = ET.parse(modxml)
    root = tree.getroot()

    module_id = int(root.get("id", 0))
    activity_type = root.findtext("modulename", "")
    section_number = int(root.findtext("sectionnumber", "0"))
    completion = int(root.findtext("completion", "0"))
    completionview = root.findtext("completionview", "0") == "1"
    completionpassgrade = root.findtext("completionpassgrade", "0") == "1"
    completiongradeitemnumber = parse_null(root.findtext("completiongradeitemnumber", ""))
    completionexpected = int(root.findtext("completionexpected", "0"))
    visible = root.findtext("visible", "1") == "1"

    # Get activity name from type-specific XML
    # Structure is: <activity><type_element><name>...</name></type_element></activity>
    type_xml = os.path.join(activity_dir, f"{activity_type}.xml")
    name = f"Unknown {activity_type}"
    if os.path.exists(type_xml):
        ttree = ET.parse(type_xml)
        troot = ttree.getroot()
        # Name is nested inside the type element (e.g. <activity><quiz><name>)
        name_el = troot.find(f".//{activity_type}/name")
        if name_el is not None and name_el.text:
            name = name_el.text
        else:
            # Fallback: try direct child
            name = troot.findtext("name", name)

    # Look up section name
    section_name = ""
    if section_number in sections_lookup:
        section_name = sections_lookup[section_number]["name"]

    # Get extra completion rules from type-specific XML
    # Fields are nested inside the type element (e.g. <activity><quiz><field>)
    extra_rules = {}
    if os.path.exists(type_xml):
        ttree = ET.parse(type_xml)
        troot = ttree.getroot()
        # Find the type-specific element
        type_el = troot.find(activity_type)
        if type_el is None:
            type_el = troot  # fallback

        if activity_type == "scorm":
            sr = parse_null(type_el.findtext("completionstatusrequired"))
            if sr is not None:
                extra_rules["completionstatusrequired"] = sr
            scr = parse_null(type_el.findtext("completionscorerequired"))
            if scr is not None:
                extra_rules["completionscorerequired"] = scr

        elif activity_type == "quiz":
            ae = type_el.findtext("completionattemptsexhausted", "0")
            if ae == "1":
                extra_rules["completionattemptsexhausted"] = True
            ma = type_el.findtext("completionminattempts", "0")
            if ma and ma != "0":
                extra_rules["completionminattempts"] = ma
            attempts = type_el.findtext("attempts_number", "0")
            if attempts and attempts != "0":
                extra_rules["max_attempts"] = attempts
            grade = parse_null(type_el.findtext("grade"))
            if grade:
                extra_rules["quiz_maxgrade"] = grade

        elif activity_type == "assign":
            cs = type_el.findtext("completionsubmit", "0")
            if cs == "1":
                extra_rules["completionsubmit"] = True

        elif activity_type == "forum":
            cd = type_el.findtext("completiondiscussions", "0")
            if cd and cd != "0":
                extra_rules["completiondiscussions"] = cd
            cr = type_el.findtext("completionreplies", "0")
            if cr and cr != "0":
                extra_rules["completionreplies"] = cr
            cp = type_el.findtext("completionposts", "0")
            if cp and cp != "0":
                extra_rules["completionposts"] = cp

    # Get grade pass info
    gradepass = ""
    grademax = ""
    gradesxml = os.path.join(activity_dir, "grades.xml")
    if os.path.exists(gradesxml):
        gtree = ET.parse(gradesxml)
        groot = gtree.getroot()
        gi = groot.find(".//grade_item")
        if gi is not None:
            gp = parse_null(gi.findtext("gradepass"))
            if gp:
                gradepass = gp
            gm = parse_null(gi.findtext("grademax"))
            if gm:
                grademax = gm

    return ActivityCompletion(
        module_id=module_id,
        activity_type=activity_type,
        name=name,
        section_number=section_number,
        section_name=section_name,
        visible=visible,
        completion=completion,
        completionview=completionview,
        completionpassgrade=completionpassgrade,
        completiongradeitemnumber=completiongradeitemnumber,
        completionexpected=completionexpected,
        extra_rules=extra_rules,
        gradepass=gradepass,
        grademax=grademax,
    )


def parse_course_completion(tmpdir, sections):
    """Parse all completion data from an extracted MBZ."""
    config = CourseCompletionConfig()

    # Parse course.xml
    course_xml = os.path.join(tmpdir, "course", "course.xml")
    if os.path.exists(course_xml):
        tree = ET.parse(course_xml)
        root = tree.getroot()
        config.course_id = root.get("id", "")
        config.course_shortname = root.findtext("shortname", "")
        config.course_fullname = root.findtext("fullname", "")
        config.completion_enabled = root.findtext("enablecompletion", "0") == "1"
        config.show_completion_conditions = root.findtext("showcompletionconditions", "0") == "1"
        # Check custom fields
        for cf in root.findall(".//customfield"):
            if cf.findtext("shortname") == "completion_opt_in":
                config.completion_opt_in = cf.findtext("value", "0") == "1"

    config.backup_date = parse_backup_date(tmpdir)
    config.sections = sections

    # Parse completion.xml (course-level criteria)
    completion_xml = os.path.join(tmpdir, "completion.xml")
    if os.path.exists(completion_xml):
        tree = ET.parse(completion_xml)
        root = tree.getroot()

        # Aggregation methods
        for aggr in root.findall("course_completion_aggr_methd"):
            ct = parse_null(aggr.findtext("criteriatype"))
            method = int(aggr.findtext("method", "0"))
            key = f"type_{ct}" if ct else "overall"
            config.aggregation[key] = COMPLETION_AGGREGATION.get(method, f"Unknown ({method})")

        # Criteria
        for crit in root.findall("course_completion_criteria"):
            ctype = int(crit.findtext("criteriatype", "0"))
            cc = CourseCriteria(
                criteria_id=int(crit.get("id", 0)),
                criteriatype=ctype,
                criteriatype_name=COMPLETION_CRITERIA_TYPES.get(ctype, f"Unknown ({ctype})"),
                module=crit.findtext("module", "") or "",
                moduleinstance=int(crit.findtext("moduleinstance", "0") or 0),
                gradepass=parse_null(crit.findtext("gradepass")) or "",
                enrolperiod=parse_null(crit.findtext("enrolperiod")) or "",
                timeend=parse_null(crit.findtext("timeend")) or "",
            )
            config.criteria.append(cc)

    # Parse activities
    activities_dir = os.path.join(tmpdir, "activities")
    if os.path.isdir(activities_dir):
        for actdir_name in sorted(os.listdir(activities_dir)):
            actdir = os.path.join(activities_dir, actdir_name)
            if not os.path.isdir(actdir):
                continue
            ac = parse_activity_completion(actdir, sections)
            if ac:
                config.activities.append(ac)
                config.all_activity_ids.add(ac.module_id)

    # Resolve activity names in course criteria
    activity_map = {a.module_id: a for a in config.activities}
    for crit in config.criteria:
        if crit.criteriatype == 4 and crit.moduleinstance in activity_map:
            crit.activity_name = activity_map[crit.moduleinstance].name

    return config


def format_grade(value):
    """Format a grade value, stripping trailing zeros."""
    if not value:
        return ""
    try:
        f = float(value)
        if f == int(f):
            return str(int(f))
        return f"{f:.1f}"
    except (ValueError, TypeError):
        return str(value)


def print_report(config, label=""):
    """Print a human-readable completion audit report."""
    header = f"COMPLETION AUDIT: {config.course_fullname}"
    if label:
        header += f" ({label})"
    print("=" * len(header))
    print(header)
    print("=" * len(header))
    print()

    print(f"  Course ID:       {config.course_id}")
    print(f"  Short name:      {config.course_shortname}")
    print(f"  Backup date:     {config.backup_date}")
    print(f"  Completion:      {'ENABLED' if config.completion_enabled else 'DISABLED'}")
    print(f"  Show conditions: {'Yes' if config.show_completion_conditions else 'No'}")
    print(f"  ELM opt-in:      {'Yes' if config.completion_opt_in else 'No'}")
    print()

    # Course-level criteria
    if config.criteria:
        print("COURSE COMPLETION CRITERIA")
        print("-" * 60)
        overall_agg = config.aggregation.get("overall", "All")
        print(f"  Overall aggregation: {overall_agg} criteria must be met")
        print()
        for crit in config.criteria:
            type_agg = config.aggregation.get(f"type_{crit.criteriatype}", "All")
            desc = f"  - [{crit.criteriatype_name}]"
            if crit.criteriatype == 4:  # Activity completion
                name = crit.activity_name or f"{crit.module} (id:{crit.moduleinstance})"
                desc += f" {name}"
            if crit.gradepass:
                desc += f" (pass grade: {format_grade(crit.gradepass)})"
            print(desc)
        # Show aggregation per type if multiple of same type
        type_counts = {}
        for crit in config.criteria:
            type_counts[crit.criteriatype] = type_counts.get(crit.criteriatype, 0) + 1
        for ct, count in type_counts.items():
            if count > 1:
                type_agg = config.aggregation.get(f"type_{ct}", "All")
                print(f"    -> {COMPLETION_CRITERIA_TYPES.get(ct, '?')} aggregation: {type_agg} of {count} must be met")
        print()
    else:
        print("COURSE COMPLETION CRITERIA")
        print("-" * 60)
        print("  ** No course-level completion criteria defined **")
        print()

    # Activities with completion tracking, grouped by section
    tracked = [a for a in config.activities if a.completion > 0]
    untracked = [a for a in config.activities if a.completion == 0]

    if tracked:
        print("ACTIVITIES WITH COMPLETION TRACKING")
        print("-" * 60)

        # Group by section
        by_section = {}
        for a in tracked:
            by_section.setdefault(a.section_number, []).append(a)

        for sec_num in sorted(by_section.keys()):
            sec_info = config.sections.get(sec_num, {})
            sec_name = sec_info.get("name", f"Section {sec_num}")
            sec_visible = sec_info.get("visible", True)
            vis_tag = "" if sec_visible else " [HIDDEN]"
            print(f"\n  Section {sec_num}: {sec_name}{vis_tag}")
            print(f"  {'~' * 50}")

            for a in by_section[sec_num]:
                tracking = COMPLETION_TRACKING.get(a.completion, "Unknown")
                vis = "" if a.visible else " [HIDDEN]"
                criteria_on_course = any(
                    c.criteriatype == 4 and c.moduleinstance == a.module_id
                    for c in config.criteria
                )
                course_crit = " *COURSE CRITERIA*" if criteria_on_course else ""

                print(f"    [{a.activity_type}] {a.name}{vis}{course_crit}")
                print(f"      Tracking: {tracking}")

                conditions = []
                if a.completionview:
                    conditions.append("Student must view")
                if a.completionpassgrade:
                    gp = format_grade(a.gradepass)
                    gm = format_grade(a.grademax)
                    grade_info = f"Student must achieve passing grade"
                    if gp and gm:
                        grade_info += f" ({gp}/{gm})"
                    elif gp:
                        grade_info += f" (>= {gp})"
                    conditions.append(grade_info)
                elif a.completiongradeitemnumber is not None:
                    conditions.append("Student must receive a grade")

                for key, val in a.extra_rules.items():
                    if key == "completionstatusrequired":
                        status_map = {1: "Completed", 2: "Passed", 4: "Failed"}
                        conditions.append(f"SCORM status required: {status_map.get(int(val), val)}")
                    elif key == "completionscorerequired":
                        conditions.append(f"SCORM score required: >= {val}")
                    elif key == "completionsubmit":
                        conditions.append("Student must submit")
                    elif key == "completionattemptsexhausted":
                        conditions.append("All attempts exhausted")
                    elif key == "completionminattempts":
                        conditions.append(f"Minimum {val} attempt(s)")
                    elif key == "completiondiscussions":
                        conditions.append(f"Create {val} discussion(s)")
                    elif key == "completionreplies":
                        conditions.append(f"Post {val} reply/replies")
                    elif key == "completionposts":
                        conditions.append(f"Post {val} post(s)")

                if conditions:
                    print(f"      Conditions: {'; '.join(conditions)}")

                if a.completionexpected:
                    dt = datetime.fromtimestamp(a.completionexpected)
                    print(f"      Expected by: {dt.strftime('%Y-%m-%d')}")

        print()

    # Summary stats
    total = len(config.activities)
    print("SUMMARY")
    print("-" * 60)
    print(f"  Total activities:         {total}")
    print(f"  With completion tracking: {len(tracked)}")
    print(f"    - Manual:               {sum(1 for a in tracked if a.completion == 1)}")
    print(f"    - Automatic:            {sum(1 for a in tracked if a.completion == 2)}")
    print(f"  Without tracking:         {len(untracked)}")
    print(f"  Course criteria count:    {len(config.criteria)}")

    # Count by type
    if tracked:
        types = {}
        for a in tracked:
            types[a.activity_type] = types.get(a.activity_type, 0) + 1
        print(f"  Tracked by type:          {', '.join(f'{t}={c}' for t, c in sorted(types.items()))}")

    # Hidden activities with tracking (potential issue)
    hidden_tracked = [a for a in tracked if not a.visible]
    if hidden_tracked:
        print(f"\n  WARNING: {len(hidden_tracked)} hidden activities have completion tracking:")
        for a in hidden_tracked:
            print(f"    - [{a.activity_type}] {a.name}")

    # Hidden sections with tracked activities
    for sec_num in sorted(by_section.keys()) if tracked else []:
        sec_info = config.sections.get(sec_num, {})
        if not sec_info.get("visible", True):
            sec_acts = [a for a in by_section[sec_num] if a.visible]
            if sec_acts:
                print(f"\n  NOTE: Section {sec_num} ({sec_info.get('name', '')}) is hidden but contains {len(sec_acts)} tracked activities")

    # Completion enabled but no criteria
    if config.completion_enabled and not config.criteria:
        print("\n  WARNING: Course completion is enabled but NO course-level criteria are defined.")
        print("           Students cannot complete this course through any criteria path.")

    # Criteria referencing activities
    if config.criteria:
        for crit in config.criteria:
            if crit.criteriatype == 4:
                act = next((a for a in config.activities if a.module_id == crit.moduleinstance), None)
                if act is None:
                    print(f"\n  WARNING: Course criterion references missing activity (id:{crit.moduleinstance})")
                elif not act.visible:
                    print(f"\n  WARNING: Course criterion references hidden activity: {act.name}")

    print()


def print_comparison(old_config, new_config):
    """Print a comparison report between two backups."""
    print()
    print("=" * 70)
    print("COMPARISON: Changes Between Backups")
    print("=" * 70)
    print(f"  OLD: {old_config.backup_date}")
    print(f"  NEW: {new_config.backup_date}")
    print()

    changes = []

    # Course-level changes
    if old_config.completion_enabled != new_config.completion_enabled:
        old_val = "Enabled" if old_config.completion_enabled else "Disabled"
        new_val = "Enabled" if new_config.completion_enabled else "Disabled"
        changes.append(f"Course completion tracking: {old_val} -> {new_val}")

    if old_config.completion_opt_in != new_config.completion_opt_in:
        old_val = "Yes" if old_config.completion_opt_in else "No"
        new_val = "Yes" if new_config.completion_opt_in else "No"
        changes.append(f"ELM completion opt-in: {old_val} -> {new_val}")

    if old_config.course_fullname != new_config.course_fullname:
        changes.append(f"Course name: \"{old_config.course_fullname}\" -> \"{new_config.course_fullname}\"")

    # Course criteria changes
    old_crit_keys = {(c.criteriatype, c.moduleinstance) for c in old_config.criteria}
    new_crit_keys = {(c.criteriatype, c.moduleinstance) for c in new_config.criteria}

    removed_crit = old_crit_keys - new_crit_keys
    added_crit = new_crit_keys - old_crit_keys

    if removed_crit or added_crit:
        changes.append("")
        changes.append("COURSE COMPLETION CRITERIA CHANGES:")
        old_crit_map = {(c.criteriatype, c.moduleinstance): c for c in old_config.criteria}
        new_crit_map = {(c.criteriatype, c.moduleinstance): c for c in new_config.criteria}

        for key in sorted(removed_crit):
            crit = old_crit_map[key]
            name = crit.activity_name or f"{crit.module} (id:{crit.moduleinstance})"
            changes.append(f"  REMOVED: [{crit.criteriatype_name}] {name}")

        for key in sorted(added_crit):
            crit = new_crit_map[key]
            name = crit.activity_name or f"{crit.module} (id:{crit.moduleinstance})"
            changes.append(f"  ADDED:   [{crit.criteriatype_name}] {name}")

    # Activity changes
    old_acts = {a.module_id: a for a in old_config.activities}
    new_acts = {a.module_id: a for a in new_config.activities}

    removed_ids = old_config.all_activity_ids - new_config.all_activity_ids
    added_ids = new_config.all_activity_ids - old_config.all_activity_ids
    common_ids = old_config.all_activity_ids & new_config.all_activity_ids

    if removed_ids:
        removed_tracked = [old_acts[i] for i in sorted(removed_ids) if i in old_acts and old_acts[i].completion > 0]
        removed_untracked = [old_acts[i] for i in sorted(removed_ids) if i in old_acts and old_acts[i].completion == 0]

        if removed_tracked or removed_untracked:
            changes.append("")
            changes.append(f"ACTIVITIES REMOVED ({len(removed_ids)} total):")
            if removed_tracked:
                changes.append(f"  With completion tracking ({len(removed_tracked)}):")
                for a in removed_tracked:
                    tracking = COMPLETION_TRACKING.get(a.completion, "Unknown")
                    was_criteria = any(c.criteriatype == 4 and c.moduleinstance == a.module_id for c in old_config.criteria)
                    crit_tag = " **WAS COURSE CRITERIA**" if was_criteria else ""
                    changes.append(f"    - [{a.activity_type}] {a.name} (tracking: {tracking}){crit_tag}")
            if removed_untracked:
                changes.append(f"  Without completion tracking ({len(removed_untracked)}):")
                for a in removed_untracked:
                    changes.append(f"    - [{a.activity_type}] {a.name}")

    if added_ids:
        added_tracked = [new_acts[i] for i in sorted(added_ids) if i in new_acts and new_acts[i].completion > 0]
        added_untracked = [new_acts[i] for i in sorted(added_ids) if i in new_acts and new_acts[i].completion == 0]

        if added_tracked or added_untracked:
            changes.append("")
            changes.append(f"ACTIVITIES ADDED ({len(added_ids)} total):")
            if added_tracked:
                changes.append(f"  With completion tracking ({len(added_tracked)}):")
                for a in added_tracked:
                    tracking = COMPLETION_TRACKING.get(a.completion, "Unknown")
                    changes.append(f"    - [{a.activity_type}] {a.name} (tracking: {tracking})")
            if added_untracked:
                changes.append(f"  Without completion tracking ({len(added_untracked)}):")
                for a in added_untracked:
                    changes.append(f"    - [{a.activity_type}] {a.name}")

    # Completion tracking changes on common activities
    tracking_changes = []
    for mid in sorted(common_ids):
        if mid not in old_acts or mid not in new_acts:
            continue
        old_a = old_acts[mid]
        new_a = new_acts[mid]

        diffs = []
        if old_a.completion != new_a.completion:
            diffs.append(f"tracking: {COMPLETION_TRACKING[old_a.completion]} -> {COMPLETION_TRACKING[new_a.completion]}")
        if old_a.completionview != new_a.completionview:
            diffs.append(f"view required: {old_a.completionview} -> {new_a.completionview}")
        if old_a.completionpassgrade != new_a.completionpassgrade:
            diffs.append(f"pass grade: {old_a.completionpassgrade} -> {new_a.completionpassgrade}")
        if old_a.visible != new_a.visible:
            diffs.append(f"visible: {old_a.visible} -> {new_a.visible}")
        if old_a.section_number != new_a.section_number:
            diffs.append(f"moved: section {old_a.section_number} -> section {new_a.section_number}")

        if diffs:
            tracking_changes.append((new_a, diffs))

    if tracking_changes:
        changes.append("")
        changes.append("COMPLETION SETTINGS CHANGED ON EXISTING ACTIVITIES:")
        for a, diffs in tracking_changes:
            changes.append(f"  [{a.activity_type}] {a.name}")
            for d in diffs:
                changes.append(f"    - {d}")

    # Section visibility changes
    sec_changes = []
    for sec_num in sorted(set(list(old_config.sections.keys()) + list(new_config.sections.keys()))):
        old_sec = old_config.sections.get(sec_num, {})
        new_sec = new_config.sections.get(sec_num, {})
        if old_sec.get("visible") != new_sec.get("visible"):
            old_vis = "visible" if old_sec.get("visible", True) else "hidden"
            new_vis = "visible" if new_sec.get("visible", True) else "hidden"
            name = new_sec.get("name") or old_sec.get("name") or f"Section {sec_num}"
            sec_changes.append(f"  Section {sec_num} ({name}): {old_vis} -> {new_vis}")

    if sec_changes:
        changes.append("")
        changes.append("SECTION VISIBILITY CHANGES:")
        for sc in sec_changes:
            changes.append(sc)

    # Print all changes
    if changes:
        for line in changes:
            print(line)
    else:
        print("  No completion-related changes detected.")

    # Impact assessment
    print()
    print("IMPACT ASSESSMENT")
    print("-" * 70)

    # Check if course criteria were removed
    if removed_crit and not added_crit and not new_config.criteria:
        print("  CRITICAL: All course completion criteria have been removed.")
        print("  - Students can no longer complete this course through any criteria path.")
        print("  - Existing completions are preserved, but new completions cannot occur.")
        if new_config.completion_opt_in:
            print("  - ELM opt-in is ENABLED: completion data will NOT be sent to ELM")
            print("    because no students can achieve course completion.")

    elif removed_crit:
        print(f"  {len(removed_crit)} course completion criteria were removed.")
        remaining = len(new_config.criteria)
        overall_agg = new_config.aggregation.get("overall", "All")
        print(f"  {remaining} criteria remain with '{overall_agg}' aggregation.")

    # Check for removed activities that were criteria
    criteria_activities_removed = [
        old_acts[i] for i in removed_ids
        if i in old_acts and any(c.criteriatype == 4 and c.moduleinstance == i for c in old_config.criteria)
    ]
    if criteria_activities_removed:
        print()
        print("  WARNING: Activities that were course completion criteria have been removed:")
        for a in criteria_activities_removed:
            print(f"    - {a.name}")
        print("  This means those criteria can no longer be satisfied.")

    # Check for opt-in change
    if old_config.completion_opt_in != new_config.completion_opt_in:
        if new_config.completion_opt_in:
            print()
            print("  NOTABLE: ELM completion opt-in has been ENABLED.")
            print("  Course completions will now be sent to ELM via the psaelmsync plugin.")
        else:
            print()
            print("  NOTABLE: ELM completion opt-in has been DISABLED.")
            print("  Course completions will no longer be sent to ELM.")

    # Overall completion path comparison
    old_tracked = [a for a in old_config.activities if a.completion > 0]
    new_tracked = [a for a in new_config.activities if a.completion > 0]
    print()
    print(f"  Tracked activities: {len(old_tracked)} -> {len(new_tracked)}")
    print(f"  Course criteria: {len(old_config.criteria)} -> {len(new_config.criteria)}")
    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    mbz_files = sys.argv[1:]

    if len(mbz_files) > 2:
        print("Error: Maximum 2 MBZ files (old and new for comparison).")
        sys.exit(1)

    for f in mbz_files:
        if not os.path.exists(f):
            print(f"Error: File not found: {f}")
            sys.exit(1)

    configs = []
    tmpdirs = []

    for mbz_file in mbz_files:
        print(f"Extracting {os.path.basename(mbz_file)}...", file=sys.stderr)
        tmpdir = extract_mbz(mbz_file)
        tmpdirs.append(tmpdir)
        sections = parse_sections(tmpdir)
        config = parse_course_completion(tmpdir, sections)
        configs.append(config)

    if len(configs) == 1:
        print_report(configs[0])
    else:
        # Print both reports, then comparison
        print_report(configs[0], label="OLD")
        print_report(configs[1], label="NEW")
        print_comparison(configs[0], configs[1])

    # Cleanup
    import shutil
    for tmpdir in tmpdirs:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
