from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from rca_core.config import Config
from rca_core.errors import RcaError

ADO_SCOPES = ["499b84ac-1321-427f-aa17-267ca6975798/.default"]

# (client_id, tenant_id, token_cache_path) -> (cache, manual_persist, app), shared across TokenProvider instances
# so we don't rebuild the MSAL app (and re-touch the encrypted cache file) on every call.
_SESSIONS: dict[tuple[str, str, str], tuple[Any, bool, Any]] = {}


def _build_cache(path: Path) -> tuple[Any, bool]:
    """Return (token_cache, needs_manual_persist). Encrypted persistence (DPAPI on Windows) when available."""
    import msal
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


class TokenProvider:
    """Entra ID sign-in for Azure DevOps. Never prints; every message is returned to the caller."""

    def __init__(self, cfg: Config, app_factory: Callable[[Config, Any], Any] = _default_app_factory, cache: Any = None) -> None:
        if not cfg.client_id or not cfg.tenant_id:
            raise RcaError("auth_not_configured", "Browser sign-in needs the team's Entra app registration.",
                           'Set auth.client_id and auth.tenant_id in team.toml (or ~/.rca/config.toml), or set auth.mode = "pat".')
        self.cfg = cfg

        def build_app(c: Any) -> Any:
            try:
                return app_factory(cfg, c)
            except RcaError:
                raise
            except Exception as exc:
                raise RcaError("auth_unavailable", f"Could not reach Microsoft sign-in: {type(exc).__name__}: {str(exc)[:200]}",
                               "Check network or VPN access to login.microsoftonline.com and retry.")

        if cache is None:
            key = (cfg.client_id, cfg.tenant_id, str(cfg.token_cache_path))
            if key not in _SESSIONS:
                built_cache, manual_persist = _build_cache(cfg.token_cache_path)
                _SESSIONS[key] = (built_cache, manual_persist, build_app(built_cache))
            self.cache, self._manual_persist, self.app = _SESSIONS[key]
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
            if not result or "access_token" not in result:  # timed out or was cancelled: fall back to device code
                return self._start_device_flow(
                    interactive_error=str((result or {}).get("error_description") or (result or {}).get("error")
                                          or "interactive sign-in timed out"))
        self._persist()
        return {"signed_in": True, "user": self.signed_in_user()}

    def _start_device_flow(self, interactive_error: str | None = None) -> dict:
        flow = self.app.initiate_device_flow(scopes=ADO_SCOPES)
        if "user_code" not in flow:
            raise RcaError("auth_failed", "Could not start device sign-in.",
                           "Check auth.client_id/tenant_id and that public client flows are enabled on the app registration.")
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
                           "Run rca_login() again.")
        self._persist()
        return {"signed_in": True, "user": self.signed_in_user()}

    # PersistedTokenCache (encrypted/DPAPI) persists itself on every write; this only covers the plain-file fallback.
    def _persist(self) -> None:
        if self._manual_persist and getattr(self.cache, "has_state_changed", False):
            self.cfg.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cfg.token_cache_path.write_text(self.cache.serialize(), encoding="utf-8")
