import asyncio

import rca_mcp.server as srv


def test_tools_are_registered():
    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert names == {"rca_fetch", "rca_trace", "rca_classify", "rca_fields", "rca_publish"}


def test_rca_fetch_without_pat_returns_error(monkeypatch, tmp_path):
    monkeypatch.delenv("ADO_PAT", raising=False)
    monkeypatch.setattr(srv, "USER_CONFIG", tmp_path / "none.toml")
    out = srv.rca_fetch(123)
    assert out["error"]["code"] == "no_pat"


def test_rca_publish_defaults_to_dry_run(monkeypatch, tmp_path):
    seen = {}

    def fake_publish(bug_id, sections, cfg, client, dry_run=True):
        seen["dry_run"] = dry_run
        return {"dry_run": dry_run, "patch": {}}

    monkeypatch.setenv("ADO_PAT", "x")
    monkeypatch.setattr(srv, "USER_CONFIG", tmp_path / "none.toml")
    monkeypatch.setattr(srv, "publish", fake_publish)
    assert srv.rca_publish(1, {"root_cause": "r"})["dry_run"] is True
    assert seen["dry_run"] is True
