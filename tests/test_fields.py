from rca_core.fields import SECTION_KEYS, closest_field, validate_field_map

AVAILABLE = [
    {"referenceName": "Custom.RootCause", "name": "Root Cause"},
    {"referenceName": "Custom.BugClassification", "name": "Bug Classification", "allowedValues": ["Legacy Bug"]},
    {"referenceName": "Custom.LessonsLearned", "name": "Lessons Learned"},
]


def test_section_keys_are_the_thirteen_template_sections():
    assert len(SECTION_KEYS) == 13
    assert SECTION_KEYS[0] == "summary" and SECTION_KEYS[-1] == "why_missed"


def test_validate_reports_missing_with_suggestion():
    issues = validate_field_map(
        {"root_cause": "Custom.RootCause", "lesson_learned": "Custom.LessonLearned"}, AVAILABLE
    )
    assert {"section": "lesson_learned", "configured": "Custom.LessonLearned", "suggestion": "Custom.LessonsLearned"} in issues


def test_validate_reports_unconfigured_sections():
    issues = validate_field_map({}, AVAILABLE)
    assert {"section": "root_cause", "configured": "", "suggestion": "Custom.RootCause"} in issues


def test_closest_field_returns_none_when_nothing_similar():
    assert closest_field("Zebra Quotient", AVAILABLE) is None


def test_validate_reports_unconfigured_sections_even_when_map_is_partial():
    issues = validate_field_map({"summary": "Custom.Bogus"}, AVAILABLE)
    sections = {i["section"] for i in issues}
    assert "summary" in sections and "root_cause" in sections
    assert len(issues) == 13
