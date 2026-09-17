from rca_core.ado_client import AdoClient
from rca_core.cache import write_cache
from rca_core.config import load_config
from rca_core.operations.classify import classify_op
from rca_core.operations.fields import fields_op
from tests.conftest import FakeTransport


def test_classify_from_cached_trace(tmp_path):
    cfg = load_config(user_path=tmp_path / "c.toml", env={})
    cfg.home = tmp_path
    write_cache(cfg, 1, {"trace": {"bug_id": 1, "repo": "R", "evidence": [], "confidence_notes": [],
                                   "culprits": [{"sha": "a" * 40, "author": "A", "date": "d", "subject": "s", "lines": 4,
                                                 "pr_id": None, "pr_title": "", "work_items": [], "parent_chain": [],
                                                 "release_branches": ["release/9.5"], "earliest_version": "9.5"}]}})
    out = classify_op(1, cfg)
    assert out["classification"] == "Legacy Bug" and out["confidence"] == "high"


def test_classify_without_trace_errors(tmp_path):
    cfg = load_config(user_path=tmp_path / "c.toml", env={})
    cfg.home = tmp_path
    assert classify_op(2, cfg)["error"]["code"] == "fetch_first"


def test_fields_op_reports_issues(tmp_path):
    cfg = load_config(user_path=tmp_path / "c.toml", env={})
    t = FakeTransport({
        ("GET", "/workitemtypes/Bug/fields"): {"value": [{"referenceName": "Custom.RootCause", "name": "Root Cause"}]},
        ("GET", "/_apis/wit/fields?"): {"value": []},
    })
    out = fields_op(cfg, AdoClient("https://dev.azure.com/a", "P", t))
    assert out["ok"] is False
    assert out["fields"][0]["referenceName"] == "Custom.RootCause"
    assert all(i["section"] != "root_cause" for i in out["issues"])
    assert any(i["section"] == "summary" for i in out["issues"])
