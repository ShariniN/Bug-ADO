import asyncio

import rca_mcp.server as srv
from tests.fake_msal import FakeMsalApp


def test_tools_are_registered():
    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert names == {
        "rca_status", "rca_login", "rca_setup_options", "rca_save_config",
        "rca_fetch", "rca_trace", "rca_classify", "rca_fields", "rca_publish",
    }


def test_rca_fetch_not_signed_in(monkeypatch, tmp_path):
    # Team defaults now ship a ready-to-use client id/tenant id, so an unconfigured browser-mode
    # setup fails at "not signed in yet" (no account cached), not auth_not_configured. rca_fetch actually
    # builds a client (unlike status()), so it does construct an MSAL app -- fake it out to avoid network,
    # and clear the process-level session/cache memos so this test doesn't reuse another test's real app.
    monkeypatch.setattr("rca_core.auth._default_app_factory", lambda cfg, cache: FakeMsalApp())
    monkeypatch.setattr("rca_core.auth._SESSIONS", {})
    monkeypatch.setattr("rca_core.auth._CACHES", {})
    cfg_path = tmp_path / "cfg.toml"
    cfg_path.write_text('[auth]\nmode = "browser"\n', encoding="utf-8")
    monkeypatch.setattr(srv, "USER_CONFIG", cfg_path)
    out = srv.rca_fetch("1")
    assert out["error"]["code"] == "not_signed_in"


def test_rca_publish_defaults_to_dry_run(monkeypatch, tmp_path):
    seen = {}

    def fake_publish(bug_id, sections, cfg, client, dry_run=True):
        seen["dry_run"] = dry_run
        return {"dry_run": dry_run, "patch": {}}

    cfg_path = tmp_path / "cfg.toml"
    cfg_path.write_text('[auth]\nmode = "pat"\n', encoding="utf-8")
    monkeypatch.setenv("ADO_PAT", "x")
    monkeypatch.setattr(srv, "USER_CONFIG", cfg_path)
    monkeypatch.setattr(srv, "publish", fake_publish)
    assert srv.rca_publish(1, {"root_cause": "r"})["dry_run"] is True
    assert seen["dry_run"] is True
