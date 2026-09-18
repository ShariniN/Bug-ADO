from rca_core.ado_client import AdoClient
from rca_core.config import load_config
from rca_core.operations import setup
from tests.ado_routes import org_routes
from tests.conftest import FakeTransport
from tests.fake_msal import FakeMsalApp

ACC = [{"username": "jo@acme.com"}]


def cfg(tmp_path, text='[auth]\nmode = "browser"\nclient_id = "cid"\ntenant_id = "tid"\n'):
    (tmp_path / "config.toml").write_text(text, encoding="utf-8")
    return load_config(user_path=tmp_path / "config.toml", env={})


def factory(app):
    return lambda c: __import__("rca_core.auth", fromlist=["TokenProvider"]).TokenProvider(c, app_factory=lambda cfg, cache: app, cache=object())


def test_status_unconfigured_and_signed_out(tmp_path):
    # No app is built for status() any more (it reads the token cache directly), so this is signed-out
    # simply because cfg.home (== tmp_path) has no cache file yet.
    out = setup.status(cfg(tmp_path))
    assert out["signed_in"] is False and out["configured"] is False and out["user"] is None
    assert out["auth_error"] is None


def test_status_reads_account_from_cache_without_app(tmp_path, monkeypatch):
    from rca_core import auth as auth_mod

    def boom(cfg, cache):
        raise AssertionError("status() must not build an MSAL app")

    monkeypatch.setattr(auth_mod, "_default_app_factory", boom)

    class FakeCache:
        def search(self, credential_type):
            return [{"username": "jo@acme.com"}]

    c = cfg(tmp_path)
    key = (str(c.token_cache_path), c.persist_tokens)
    monkeypatch.setitem(auth_mod._CACHES, key, (FakeCache(), False))
    out = setup.status(c)
    assert out["user"] == "jo@acme.com" and out["signed_in"] is True


def test_status_survives_corrupt_cache(tmp_path, monkeypatch):
    from rca_core import auth as auth_mod

    class BoomCache:
        def search(self, credential_type):
            raise ValueError("corrupt cache")

    c = cfg(tmp_path)
    key = (str(c.token_cache_path), c.persist_tokens)
    monkeypatch.setitem(auth_mod._CACHES, key, (BoomCache(), False))
    out = setup.status(c)
    assert out["auth_error"]["code"] == "auth_unavailable"


def test_status_signed_in_pat_mode(tmp_path):
    c = cfg(tmp_path, '[ado]\norg_url = "https://dev.azure.com/acme"\nproject = "Acme"\n[auth]\nmode = "pat"\n')
    c._env = {"ADO_PAT": "x"}
    out = setup.status(c)
    assert out["signed_in"] is True and out["configured"] is True and out["auth_mode"] == "pat"


def test_login_and_options(tmp_path):
    c = cfg(tmp_path)
    app = FakeMsalApp(interactive={"access_token": "t"})
    app.accounts = ACC
    assert setup.login(c, auth_factory=factory(app)) == {"signed_in": True, "user": "jo@acme.com"}
    out = setup.options(c, AdoClient("", "", FakeTransport(org_routes())))
    assert [a["name"] for a in out["accounts"]] == ["acme", "other"] and out["projects"] == []
    c.org_url = "https://dev.azure.com/acme"
    assert setup.options(c, AdoClient(c.org_url, "", FakeTransport(org_routes())))["projects"] == ["Acme", "Beta"]


def test_save_config_round_trips_through_load_config(tmp_path):
    c = cfg(tmp_path)
    out = setup.save_config(c, org_url="https://dev.azure.com/acme/", project="Acme", fields={"summary": "Custom.S"}, current_pi="Acme\\PI-14")
    again = load_config(user_path=tmp_path / "config.toml", env={})
    assert again.org_url == "https://dev.azure.com/acme" and again.project == "Acme"
    assert again.fields["summary"] == "Custom.S" and again.current_pi == "Acme\\PI-14" and again.client_id == "cid"
    assert out["path"].endswith("config.toml")


def test_save_config_client_id_and_tenant_id_round_trip(tmp_path):
    c = cfg(tmp_path)
    setup.save_config(c, client_id="cid2", tenant_id="tid2")
    again = load_config(user_path=tmp_path / "config.toml", env={})
    assert again.client_id == "cid2" and again.tenant_id == "tid2"


def test_pat_mode_login_without_env_var_is_no_pat(tmp_path):
    c = cfg(tmp_path, '[auth]\nmode = "pat"\n')
    c._env = {}
    out = setup.login(c)
    assert out["error"]["code"] == "no_pat"


def _cfg_with_org_project(tmp_path):
    return cfg(tmp_path, '[ado]\norg_url = "https://dev.azure.com/acme"\nproject = "Acme"\n'
                          '[auth]\nmode = "browser"\nclient_id = "cid"\ntenant_id = "tid"\n')


def test_save_config_project_change_clears_bug_type(tmp_path):
    from rca_core.operations.setup import read_status, write_status

    c = _cfg_with_org_project(tmp_path)
    write_status(c, bug_type="Issue", bug_type_for=f"{c.org_url}|{c.project}", fields_ok=True)
    setup.save_config(c, project="Other")
    status = read_status(c)
    assert status.get("bug_type") is None
    assert status.get("bug_type_for") is None
    assert status.get("fields_ok") is False


def test_status_reports_cached_bug_type_for_current_project(tmp_path):
    from rca_core.operations.setup import write_status

    c = _cfg_with_org_project(tmp_path)
    write_status(c, bug_type="Issue", bug_type_for=f"{c.org_url}|{c.project}")
    out = setup.status(c)
    assert out["bug_type"] == "Issue"
