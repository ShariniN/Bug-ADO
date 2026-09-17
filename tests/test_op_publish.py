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


def cfg(tmp_path):
    return load_config(user_path=tmp_path / "c.toml", env={})


def test_dry_run_returns_patch_body(tmp_path):
    client = AdoClient("https://dev.azure.com/a", "P", FakeTransport(FIELDS))
    out = publish(100, {"root_cause": "null b", "classification": "Legacy Bug"}, cfg(tmp_path), client, dry_run=True)
    assert out == {"dry_run": True, "patch": {"Custom.RootCause": "null b", "Custom.BugClassification": "Legacy Bug"}}


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
    assert out == {"dry_run": False, "id": 100, "rev": 3, "url": "u"}
    assert t.calls[-1][0] == "PATCH"
