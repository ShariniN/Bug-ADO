import json

import rca_cli.main as cli


def test_version_prints_json(capsys):
    assert cli.main(["version"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "version" in out


def test_fetch_without_pat_reports_no_pat(monkeypatch, tmp_path, capsys):
    cfg_path = tmp_path / "cfg.toml"
    cfg_path.write_text('[auth]\nmode = "pat"\n', encoding="utf-8")
    monkeypatch.delenv("ADO_PAT", raising=False)
    monkeypatch.setattr(cli, "USER_CONFIG", cfg_path)
    assert cli.main(["fetch", "123"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "no_pat"


def test_status_runs_without_network(monkeypatch, tmp_path, capsys):
    cfg_path = tmp_path / "cfg.toml"
    cfg_path.write_text('[auth]\nmode = "browser"\n', encoding="utf-8")
    monkeypatch.setattr(cli, "USER_CONFIG", cfg_path)
    assert cli.main(["status"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "signed_in" in out
    assert out["auth_error"]["code"] == "auth_not_configured"


def test_publish_reads_sections_file_and_dry_runs(monkeypatch, tmp_path, capsys):
    calls = {}

    def fake_publish(bug_id, sections, cfg, client, dry_run=True):
        calls.update(bug_id=bug_id, sections=sections, dry_run=dry_run)
        return {"dry_run": dry_run, "patch": {}}

    cfg_path = tmp_path / "cfg.toml"
    cfg_path.write_text('[auth]\nmode = "pat"\n', encoding="utf-8")
    monkeypatch.setenv("ADO_PAT", "x")
    monkeypatch.setattr(cli, "USER_CONFIG", cfg_path)
    monkeypatch.setattr(cli, "publish", fake_publish)
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"root_cause": "r"}), encoding="utf-8")
    assert cli.main(["publish", "9", "--sections", str(f)]) == 0
    assert calls == {"bug_id": 9, "sections": {"root_cause": "r"}, "dry_run": True}
    assert json.loads(capsys.readouterr().out)["dry_run"] is True


def test_publish_missing_sections_file_is_json_error(monkeypatch, tmp_path, capsys):
    cfg_path = tmp_path / "cfg.toml"
    cfg_path.write_text('[auth]\nmode = "pat"\n', encoding="utf-8")
    monkeypatch.setenv("ADO_PAT", "x")
    monkeypatch.setattr(cli, "USER_CONFIG", cfg_path)
    assert cli.main(["publish", "9", "--sections", str(tmp_path / "nope.json")]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_sections"


def test_publish_malformed_sections_file_is_json_error(monkeypatch, tmp_path, capsys):
    cfg_path = tmp_path / "cfg.toml"
    cfg_path.write_text('[auth]\nmode = "pat"\n', encoding="utf-8")
    monkeypatch.setenv("ADO_PAT", "x")
    monkeypatch.setattr(cli, "USER_CONFIG", cfg_path)
    f = tmp_path / "bad.json"
    f.write_text("{not json", encoding="utf-8")
    assert cli.main(["publish", "9", "--sections", str(f)]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_sections"
