from pathlib import Path

import pytest

from rca_core.config import Config, load_config, merge
from rca_core.errors import RcaError


def test_merge_is_deep_and_override_wins():
    base = {"ado": {"org_url": "a", "project": "p"}, "fields": {"summary": "X"}}
    over = {"ado": {"project": "q"}, "fields": {"root_cause": "Y"}}
    out = merge(base, over)
    assert out == {"ado": {"org_url": "a", "project": "q"}, "fields": {"summary": "X", "root_cause": "Y"}}


def test_load_config_uses_team_defaults_when_no_user_file(tmp_path):
    cfg = load_config(user_path=tmp_path / "missing.toml", env={})
    assert cfg.legacy_cutoff == "9.6"
    assert cfg.release_branch_pattern == r"release/(\d+\.\d+)"
    assert cfg.fields["classification"]
    assert cfg.pat_env == "ADO_PAT"


def test_user_file_overrides_defaults(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text(
        '[ado]\norg_url = "https://dev.azure.com/acme"\nproject = "Acme"\n'
        '[git]\nlegacy_cutoff = "8.0"\ncurrent_pi = "Acme\\\\PI-3"\n'
        '[repos]\n"Acme.Web" = "C:/src/web"\n',
        encoding="utf-8",
    )
    cfg = load_config(user_path=user, env={})
    assert cfg.org_url == "https://dev.azure.com/acme"
    assert cfg.legacy_cutoff == "8.0"
    assert cfg.current_pi == "Acme\\PI-3"
    assert cfg.repos["Acme.Web"] == "C:/src/web"


def test_pat_read_from_env_and_missing_raises(tmp_path):
    cfg = load_config(user_path=tmp_path / "x.toml", env={"ADO_PAT": "secret"})
    assert cfg.pat() == "secret"
    cfg2 = load_config(user_path=tmp_path / "x.toml", env={})
    with pytest.raises(RcaError) as e:
        cfg2.pat()
    assert e.value.code == "no_pat"


def test_repo_path_errors(tmp_path):
    cfg = load_config(user_path=tmp_path / "x.toml", env={})
    with pytest.raises(RcaError) as e:
        cfg.repo_path("Nope")
    assert e.value.code == "repo_not_configured"
    cfg.repos["Nope"] = str(tmp_path / "not-here")
    with pytest.raises(RcaError) as e2:
        cfg.repo_path("Nope")
    assert e2.value.code == "repo_not_cloned"
    (tmp_path / "here" / ".git").mkdir(parents=True)
    cfg.repos["Here"] = str(tmp_path / "here")
    assert cfg.repo_path("Here") == Path(tmp_path / "here")
