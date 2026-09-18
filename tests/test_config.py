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
        '[git]\nlegacy_cutoff = "8.0"\ncurrent_pi = "Acme\\\\PI-3"\n',
        encoding="utf-8",
    )
    cfg = load_config(user_path=user, env={})
    assert cfg.org_url == "https://dev.azure.com/acme"
    assert cfg.legacy_cutoff == "8.0"
    assert cfg.current_pi == "Acme\\PI-3"


def test_pat_read_from_env_and_missing_raises(tmp_path):
    cfg = load_config(user_path=tmp_path / "x.toml", env={"ADO_PAT": "secret"})
    assert cfg.pat() == "secret"
    cfg2 = load_config(user_path=tmp_path / "x.toml", env={})
    with pytest.raises(RcaError) as e:
        cfg2.pat()
    assert e.value.code == "no_pat"


def test_auth_defaults_and_override(tmp_path):
    cfg = load_config(user_path=tmp_path / "none.toml", env={})
    assert cfg.auth_mode == "browser" and cfg.client_id == "" and cfg.token_cache_path.name == "msal_cache.bin"
    (tmp_path / "u.toml").write_text('[auth]\nmode = "pat"\nclient_id = "abc"\n', encoding="utf-8")
    cfg2 = load_config(user_path=tmp_path / "u.toml", env={})
    assert cfg2.auth_mode == "pat" and cfg2.client_id == "abc"
