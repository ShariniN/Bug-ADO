from rca_core.ado_client import AdoClient
from rca_core.config import load_config
from rca_core.operations.publish import publish
from tests.conftest import FakeTransport

FIELDS = {("GET", "/workitemtypes/Bug/fields"): {"value": [
    {"referenceName": "Custom.BugClassification", "name": "Bug Classification",
     "allowedValues": ["Legacy Bug", "Feature Bug", "Non-Feature Bug"]},
    {"referenceName": "Custom.RootCause", "name": "Root Cause", "type": "string"}]},
    ("GET", "/_apis/wit/fields?"): {"value": [
        {"referenceName": "Custom.RootCause", "type": "string"}]}}

# referenceName for every SECTION_KEYS entry, matching the team.toml defaults so a bare cfg() maps all of them.
ALL_FIELD_REFS = {
    "summary": "Custom.RCASummary", "root_cause": "Custom.RootCause", "impact": "Custom.ImpactAssessment",
    "previous_versions": "Custom.PreviousVersions", "related_ids": "Custom.RelatedIdentifiers",
    "classification": "Custom.BugClassification", "preventive_action": "Custom.PreventiveAction",
    "lesson_learned": "Custom.LessonLearned", "analysis_method": "Custom.AnalysisMethod",
    "fix_description": "Custom.FixDescription", "impacted_area": "Custom.ImpactedArea",
    "culprit_commit": "Custom.CausingCommit", "why_missed": "Custom.WhyMissed",
}
ALL_FIELDS = {("GET", "/workitemtypes/Bug/fields"): {"value": [
    {"referenceName": ref, "name": key,
     **({"allowedValues": ["Legacy Bug", "Feature Bug", "Non-Feature Bug"]} if key == "classification" else {})}
    for key, ref in ALL_FIELD_REFS.items()]},
    ("GET", "/_apis/wit/fields?"): {"value": [{"referenceName": ref, "type": "html"} for ref in ALL_FIELD_REFS.values()]}}

FULL_SECTIONS = {
    "summary": "s" * 45, "root_cause": "r" * 45, "impact": "i" * 45,
    "previous_versions": "9.5, 10.1", "related_ids": "BUG-123",
    "classification": "Legacy Bug", "preventive_action": "p" * 45, "lesson_learned": "l" * 45,
    "analysis_method": "a" * 45, "fix_description": "f" * 45, "impacted_area": "Payroll",
    "culprit_commit": "abc1234", "why_missed": "w" * 45,
}


def cfg(tmp_path):
    c = load_config(user_path=tmp_path / "c.toml", env={})
    c.bug_type = "Bug"
    return c


def test_dry_run_returns_patch_body(tmp_path):
    client = AdoClient("https://dev.azure.com/a", "P", FakeTransport(FIELDS))
    out = publish(100, {"root_cause": "null b", "classification": "Legacy Bug"}, cfg(tmp_path), client, dry_run=True)
    assert out["dry_run"] is True
    assert out["patch"] == {"Custom.RootCause": "null b", "Custom.BugClassification": "Legacy Bug"}
    assert isinstance(out["warnings"], list)


def test_unknown_section_is_field_missing(tmp_path):
    client = AdoClient("https://dev.azure.com/a", "P", FakeTransport(FIELDS))
    out = publish(100, {"bogus": "x"}, cfg(tmp_path), client, dry_run=True)
    assert out["error"]["code"] == "field_missing"


def test_bad_classification_value_is_type_mismatch(tmp_path):
    client = AdoClient("https://dev.azure.com/a", "P", FakeTransport(FIELDS))
    out = publish(100, {"classification": "Legacy"}, cfg(tmp_path), client, dry_run=True)
    assert out["error"]["code"] == "field_type_mismatch"
    assert "Legacy Bug" in out["error"]["fix"]


def test_overlong_single_line_string_value_is_type_mismatch(tmp_path):
    client = AdoClient("https://dev.azure.com/a", "P", FakeTransport(FIELDS))
    out = publish(100, {"root_cause": "x" * 300}, cfg(tmp_path), client, dry_run=True)
    assert out["error"]["code"] == "field_type_mismatch"


def test_live_publish_patches(tmp_path):
    t = FakeTransport({**FIELDS, ("PATCH", "/workitems/100?"): {"id": 100, "rev": 3, "_links": {"html": {"href": "u"}}}})
    out = publish(100, {"root_cause": "null b"}, cfg(tmp_path), AdoClient("https://dev.azure.com/a", "P", t), dry_run=False)
    assert out["dry_run"] is False and out["id"] == 100 and out["rev"] == 3 and out["url"] == "u"
    assert any(w.startswith("section 'root_cause' is very short") for w in out["warnings"])
    assert t.calls[-1][0] == "PATCH"


def test_missing_sections_are_warned(tmp_path):
    client = AdoClient("https://dev.azure.com/a", "P", FakeTransport(FIELDS))
    out = publish(100, {"root_cause": "r" * 45}, cfg(tmp_path), client, dry_run=True)
    assert "section 'summary' is missing" in out["warnings"]
    assert "section 'classification' is missing" in out["warnings"]
    assert not any(w.startswith("section 'root_cause'") for w in out["warnings"])


def test_short_root_cause_is_warned(tmp_path):
    client = AdoClient("https://dev.azure.com/a", "P", FakeTransport(FIELDS))
    out = publish(100, {"root_cause": "null b"}, cfg(tmp_path), client, dry_run=True)
    assert "section 'root_cause' is very short (6 chars)" in out["warnings"]


def test_full_valid_set_has_no_warnings(tmp_path):
    client = AdoClient("https://dev.azure.com/a", "P", FakeTransport(ALL_FIELDS))
    out = publish(100, FULL_SECTIONS, cfg(tmp_path), client, dry_run=True)
    assert out["warnings"] == []


def test_bad_classification_without_allowed_values_is_warned_not_errored(tmp_path):
    routes = {("GET", "/workitemtypes/Bug/fields"): {"value": [
        {"referenceName": "Custom.BugClassification", "name": "Bug Classification"}]},
        ("GET", "/_apis/wit/fields?"): {"value": [{"referenceName": "Custom.BugClassification", "type": "string"}]}}
    client = AdoClient("https://dev.azure.com/a", "P", FakeTransport(routes))
    out = publish(100, {"classification": "Weird Bug"}, cfg(tmp_path), client, dry_run=True)
    assert "error" not in out, out
    assert any("classification 'Weird Bug' is not one of" in w for w in out["warnings"])
