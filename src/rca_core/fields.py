from __future__ import annotations

import difflib

SECTION_LABELS: dict[str, str] = {
    "summary": "Summary of the Issue",
    "root_cause": "Root Cause",
    "impact": "Impact Assessment",
    "previous_versions": "Previous Versions",
    "related_ids": "Related Identifiers",
    "classification": "Bug Classification",
    "preventive_action": "Preventive Action",
    "lesson_learned": "Lesson Learned",
    "analysis_method": "Analysis Method",
    "fix_description": "Fix Description",
    "impacted_area": "Impacted Area",
    "culprit_commit": "Causing Commit",
    "why_missed": "Why Missed Earlier",
}
SECTION_KEYS: list[str] = list(SECTION_LABELS)


def closest_field(name: str, available: list[dict]) -> str | None:
    """Return the referenceName whose display name or reference name is closest to `name`."""
    candidates: dict[str, str] = {}
    for f in available:
        candidates[f["name"].lower()] = f["referenceName"]
        candidates[f["referenceName"].lower()] = f["referenceName"]
        candidates[f["referenceName"].split(".")[-1].lower()] = f["referenceName"]
    matches = difflib.get_close_matches(name.lower(), list(candidates), n=1, cutoff=0.6)
    return candidates[matches[0]] if matches else None


def validate_field_map(field_map: dict[str, str], available: list[dict]) -> list[dict]:
    known = {f["referenceName"] for f in available}
    issues: list[dict] = []
    for section in SECTION_KEYS:
        if section in field_map:
            configured = field_map[section]
            if configured not in known:
                hint = configured.split(".")[-1]
                issues.append({"section": section, "configured": configured, "suggestion": closest_field(hint, available)})
        elif not field_map:
            configured = ""
            hint = SECTION_LABELS[section]
            issues.append({"section": section, "configured": configured, "suggestion": closest_field(hint, available)})
    return issues
