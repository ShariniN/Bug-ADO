from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from rca_core.config import Config
from rca_core.errors import RcaError

ADO_SCOPES = ["499b84ac-1321-427f-aa17-267ca6975798/.default"]

_SIGNIN_FIX = ('Your tenant may block the shared Azure CLI sign-in (Conditional Access). Ask an admin for the '
               "team app registration (README 'Team admin') and run rca_save_config(client_id=..., tenant_id=...), "
               'or switch to PAT mode with rca_save_config(auth_mode="pat").')

# (client_id, tenant_id, token_cache_path, persist_tokens) -> app, shared across TokenProvider instances so we
# don't rebuild the MSAL app (which performs an OpenID-discovery network call) on every call.
_SESSIONS: dict[tuple[str, str, str, bool], Any] = {}

# (token_cache_path, persist_tokens) -> (cache, manual_persist), shared independently of the app so reading the
# cache (e.g. status()) never needs to build an app or touch the network.
_CACHES: dict[tuple[str, bool], tuple[Any, bool]] = {}


def _build_cache(path: Path, persist: bool = True) -> tuple[Any, bool]:
    """Return (token_cache, needs_manual_persist). Encrypted persistence (DPAPI on Windows) when available.

    When `persist` is False the cache lives only in memory for this process: never read from or written to disk.
    """
    import msal
    if not persist:
        return msal.SerializableTokenCache(), False
    try:
        from msal_extensions import PersistedTokenCache, build_encrypted_persistence
        path.parent.mkdir(parents=True, exist_ok=True)
        return PersistedTokenCache(build_encrypted_persistence(str(path))), False
    except Exception:
        cache = msal.SerializableTokenCache()
        if path.exists():
            cache.deserialize(path.read_text(encoding="utf-8"))
        return cache, True


def _default_app_factory(cfg: Config, cache: Any) -> Any:
    import msal
    return msal.PublicClientApplication(
        cfg.client_id, authority=f"https://login.microsoftonline.com/{cfg.tenant_id}", token_cache=cache)


def _get_cache(cfg: Config) -> tuple[Any, bool]:
    """Return (token_cache, needs_manual_persist), memoized per (path, persist_tokens)."""
    key = (str(cfg.token_cache_path), cfg.persist_tokens)
    if key not in _CACHES:
        _CACHES[key] = _build_cache(cfg.token_cache_path, cfg.persist_tokens)
    return _CACHES[key]


def cached_username(cfg: Config) -> str | None:
    """Signed-in account from the token cache only — no MSAL app, no network. Used by status()."""
    try:
        import msal
        cache, _ = _get_cache(cfg)
        accounts = list(cache.search(msal.TokenCache.CredentialType.ACCOUNT))
        return accounts[0].get("username") if accounts else None
    except Exception as exc:
        raise RcaError("auth_unavailable", "The saved sign-in could not be read.",
                       "Delete ~/.rca/msal_cache.bin and sign in again.",
                       debug=f"{type(exc).__name__}: {str(exc)[:200]}")


class TokenProvider:
    """Entra ID sign-in for Azure DevOps. Never prints; every message is returned to the caller."""

    def __init__(self, cfg: Config, app_factory: Callable[[Config, Any], Any] | None = None, cache: Any = None) -> None:
        if not cfg.client_id or not cfg.tenant_id:
            raise RcaError("auth_not_configured", "Browser sign-in needs the team's Entra app registration.",
                           'Set auth.client_id and auth.tenant_id in team.toml (or ~/.rca/config.toml), or set auth.mode = "pat".')
        self.cfg = cfg
        # Resolved by name at call time (not bound as a default value) so tests can monkeypatch
        # rca_core.auth._default_app_factory even when the caller doesn't pass app_factory explicitly.
        app_factory = app_factory or _default_app_factory

        def build_app(c: Any) -> Any:
            try:
                return app_factory(cfg, c)
            except RcaError:
                raise
            except Exception as exc:
                raise RcaError("auth_unavailable", f"Could not reach Microsoft sign-in: {type(exc).__name__}: {str(exc)[:200]}",
                               "Check network or VPN access to login.microsoftonline.com and retry.")

        if cache is None:
            self.cache, self._manual_persist = _get_cache(cfg)
            key = (cfg.client_id, cfg.tenant_id, str(cfg.token_cache_path), cfg.persist_tokens)
            if key not in _SESSIONS:
                _SESSIONS[key] = build_app(self.cache)
            self.app = _SESSIONS[key]
        else:
            self.cache, self._manual_persist = cache, False
            self.app = build_app(self.cache)
        self.flow_path = cfg.home / "device_flow.json"

    def _account(self) -> dict | None:
        accounts = self.app.get_accounts()
        return accounts[0] if accounts else None

    def signed_in_user(self) -> str | None:
        acc = self._account()
        return acc.get("username") if acc else None

    def _silent(self) -> dict | None:
        acc = self._account()
        return self.app.acquire_token_silent(ADO_SCOPES, account=acc) if acc else None

    def token(self) -> str:
        result = self._silent()
        if result and "access_token" in result:
            self._persist()
            return result["access_token"]
        raise RcaError("not_signed_in", "You are not signed in to Azure DevOps.",
                       "Run /rca-setup (or the rca_login tool) to sign in with your work account.")

    def login(self, complete: bool = False) -> dict:
        if complete:
            return self._complete_device_flow()
        result = self._silent()
        if not (result and "access_token" in result):
            try:
                result = self.app.acquire_token_interactive(ADO_SCOPES, prompt="select_account", timeout=180)
            except Exception as exc:  # no browser or no free localhost port: use the device-code flow
                return self._start_device_flow(interactive_error=f"{type(exc).__name__}: {str(exc)[:200]}")
            if not result or "access_token" not in result:
                result = result or {}
                error, description = result.get("error"), result.get("error_description", "") or ""
                timeout_or_cancel = error in ("timeout", "access_denied", "user_cancelled") or "timed out" in description
                if "error" in result and not timeout_or_cancel:
                    raise RcaError(
                        "auth_failed",
                        f"Microsoft sign-in was refused: {result.get('error_description', result.get('error'))[:300]}",
                        _SIGNIN_FIX, debug=str(result.get("error")))
                # timed out or was cancelled: fall back to device code
                return self._start_device_flow(
                    interactive_error=str(result.get("error_description") or result.get("error")
                                          or "interactive sign-in timed out"))
        self._persist()
        return {"signed_in": True, "user": self.signed_in_user()}

    def _start_device_flow(self, interactive_error: str | None = None) -> dict:
        flow = self.app.initiate_device_flow(scopes=ADO_SCOPES)
        if "user_code" not in flow:
            raise RcaError("auth_failed", "Could not start device sign-in.", _SIGNIN_FIX)
        self.flow_path.parent.mkdir(parents=True, exist_ok=True)
        self.flow_path.write_text(json.dumps(flow), encoding="utf-8")
        return {"signed_in": False, "device_code_message": flow["message"],
                "verification_uri": flow["verification_uri"], "user_code": flow["user_code"],
                "interactive_error": interactive_error}

    def _complete_device_flow(self) -> dict:
        if not self.flow_path.exists():
            raise RcaError("not_signed_in", "No device sign-in is in progress.", "Call rca_login() first.")
        flow = json.loads(self.flow_path.read_text(encoding="utf-8"))
        result = self.app.acquire_token_by_device_flow(flow)
        self.flow_path.unlink(missing_ok=True)
        if not result or "access_token" not in result:
            raise RcaError("auth_failed", f"Device sign-in failed: {(result or {}).get('error_description', '')[:300]}",
                           _SIGNIN_FIX)
        self._persist()
        return {"signed_in": True, "user": self.signed_in_user()}

    def invalidate(self) -> None:
        """Forget the cached account (after a 401) so the next call asks the user to sign in again."""
        for acc in list(self.app.get_accounts()):
            self.app.remove_account(acc)
        self._persist()

    # PersistedTokenCache (encrypted/DPAPI) persists itself on every write; this only covers the plain-file fallback.
    def _persist(self) -> None:
        if self._manual_persist and getattr(self.cache, "has_state_changed", False):
            self.cfg.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cfg.token_cache_path.write_text(self.cache.serialize(), encoding="utf-8")
