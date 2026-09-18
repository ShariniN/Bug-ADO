from types import SimpleNamespace

import pytest

from rca_core.ado_client import RequestsTransport
from rca_core.auth import TokenProvider
from rca_core.config import load_config
from rca_core.errors import RcaError
from rca_core.session import build_client
from tests.fake_msal import FakeMsalApp

ACC = [{"username": "jo@acme.com", "home_account_id": "h"}]
TOK = {"access_token": "at-1"}


def cfg(tmp_path, mode="browser", client_id="cid", tenant_id="tid"):
    (tmp_path / "c.toml").write_text(
        f'[auth]\nmode = "{mode}"\nclient_id = "{client_id}"\ntenant_id = "{tenant_id}"\n', encoding="utf-8")
    return load_config(user_path=tmp_path / "c.toml", env={})


def provider(tmp_path, app, **kw):
    return TokenProvider(cfg(tmp_path, **kw), app_factory=lambda c, cache: app, cache=object())


def test_token_uses_silent_when_signed_in(tmp_path):
    app = FakeMsalApp(accounts=ACC, silent=TOK)
    assert provider(tmp_path, app).token() == "at-1"
    assert app.calls == ["silent"]


def test_token_raises_not_signed_in(tmp_path):
    with pytest.raises(RcaError) as e:
        provider(tmp_path, FakeMsalApp()).token()
    assert e.value.code == "not_signed_in"


def test_login_opens_browser_then_reports_user(tmp_path):
    app = FakeMsalApp(interactive=TOK)
    tp = provider(tmp_path, app)
    app.accounts = ACC  # msal adds the account to the cache after interactive login
    assert tp.login() == {"signed_in": True, "user": "jo@acme.com"}
    assert "interactive" in app.calls


def test_login_falls_back_to_device_flow_in_two_steps(tmp_path):
    app = FakeMsalApp(raise_interactive=True, device=TOK)
    tp = provider(tmp_path, app)
    first = tp.login()
    assert first["signed_in"] is False and first["user_code"] == "ABCD-EFGH" and "devicelogin" in first["verification_uri"]
    assert "no browser" in first["interactive_error"]
    assert (tp.cfg.home / "device_flow.json").exists()
    app.accounts = ACC
    assert tp.login(complete=True) == {"signed_in": True, "user": "jo@acme.com"}
    assert not (tp.cfg.home / "device_flow.json").exists()


def test_missing_app_registration_is_auth_not_configured(tmp_path):
    with pytest.raises(RcaError) as e:
        provider(tmp_path, FakeMsalApp(), client_id="")
    assert e.value.code == "auth_not_configured"


def test_transport_sends_bearer_from_provider():
    tr = RequestsTransport(token_provider=lambda: "tok")
    seen = {}

    def fake(method, url, json=None, headers=None, timeout=None):
        seen.update(headers=headers)
        return SimpleNamespace(status_code=200, content=b"{}", text="{}", json=lambda: {})

    tr.session.request = fake
    tr.request("GET", "https://x")
    assert seen["headers"]["Authorization"] == "Bearer tok"


def test_transport_get_text_returns_none_on_404():
    tr = RequestsTransport(pat="p")
    tr.session.request = lambda *a, **k: SimpleNamespace(status_code=404, content=b"", text="")
    assert tr.get_text("https://x/items") is None


def test_build_client_pat_mode(tmp_path):
    c = cfg(tmp_path, mode="pat")
    c._env = {"ADO_PAT": "p"}
    client, auth = build_client(c)
    assert auth is None and client.t.session.headers["Authorization"].startswith("Basic ")


def test_build_client_browser_mode_is_lazy(tmp_path):
    client, auth = build_client(cfg(tmp_path), app_factory=lambda c, cache: FakeMsalApp())
    assert auth is not None and auth.signed_in_user() is None
