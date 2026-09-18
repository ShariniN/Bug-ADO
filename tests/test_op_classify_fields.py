import tomllib

from rca_core.ado_client import AdoClient
from rca_core.cache import write_cache
from rca_core.config import load_config
from rca_core.operations.classify import classify_op
from rca_core.operations.fields import fields_op
from tests.conftest import FakeTransport
from tests.test_iterations import TREE


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


def test_classify_detects_current_pi_when_not_configured(tmp_path):
    cfg = load_config(user_path=tmp_path / "c.toml", env={})
    cfg.home = tmp_path
    write_cache(cfg, 3, {"trace": {"bug_id": 3, "repo": "R", "evidence": [], "confidence_notes": [],
                                   "culprits": [{"sha": "a" * 40, "author": "A", "date": "d", "subject": "s", "lines": 4,
                                                 "pr_id": 7, "pr_title": "t", "work_items": [],
                                                 "parent_chain": [{"id": 600, "type": "Feature", "title": "Payroll v2",
                                                                   "iteration": "Acme\\PI-14\\Sprint 4", "state": "Active"}],
                                                 "release_branches": ["release/10.1"], "earliest_version": "10.1"}]}})
    t = FakeTransport({("GET", "/classificationnodes/Iterations"): TREE})
    client = AdoClient("https://dev.azure.com/acme", "Acme", t)
    out = classify_op(3, cfg, client=client, today="2026-09-18")
    assert out["classification"] == "Feature Bug" and out["confidence"] == "high"
    assert out["detected_pi"] == "Acme\\PI-14"


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


def test_fields_op_auto_maps_exact_names(tmp_path):
    (tmp_path / "config.toml").write_text('[fields]\nsummary = "Custom.Wrong"\n', encoding="utf-8")
    cfg = load_config(user_path=tmp_path / "config.toml", env={})
    cfg.home = tmp_path
    t = FakeTransport({
        ("GET", "/workitemtypes/Bug/fields"): {"value": [{"referenceName": "Custom.Summ", "name": "Summary of the Issue"},
                                                          {"referenceName": "Custom.RootCause", "name": "Root Cause"}]},
        ("GET", "/_apis/wit/fields?"): {"value": []}})
    out = fields_op(cfg, AdoClient("https://dev.azure.com/a", "P", t), auto_map=True)
    assert out["auto_mapped"] == {"summary": "Custom.Summ"}
    assert all(i["section"] not in ("summary", "root_cause") for i in out["issues"])
    assert load_config(user_path=tmp_path / "config.toml", env={}).fields["summary"] == "Custom.Summ"
    assert (tmp_path / "status.json").exists()
    written = tomllib.loads((tmp_path / "config.toml").read_text(encoding="utf-8"))
    assert set(written["fields"]) == {"summary"}
