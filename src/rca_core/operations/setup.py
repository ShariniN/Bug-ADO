from __future__ import annotations

import json
import tomllib
from typing import Callable

from rca_core.ado_client import AdoClient
from rca_core.auth import TokenProvider, cached_username
from rca_core.config import Config, merge
from rca_core.errors import RcaError, guarded
from rca_core.tomlwrite import dumps
from rca_core.update_check import current_version


def _user_path(cfg: Config):
    return cfg.home / "config.toml"


def read_status(cfg: Config) -> dict:
    p = cfg.home / "status.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def write_status(cfg: Config, **kv) -> dict:
    merged = {**read_status(cfg), **kv}
    p = cfg.home / "status.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(merged), encoding="utf-8")
    return merged


@guarded
def status(cfg: Config) -> dict:
    """Never constructs a TokenProvider (which would build an MSAL app and hit the network for OpenID discovery):
    reads the signed-in account straight from the token cache."""
    user, signed_in, auth_error = None, False, None
    if cfg.auth_mode == "pat":
        signed_in = bool(cfg._env.get(cfg.pat_env))
        user = f"PAT ({cfg.pat_env})" if signed_in else None
    elif not cfg.client_id or not cfg.tenant_id:
        auth_error = RcaError(
            "auth_not_configured", "Browser sign-in needs the team's Entra app registration.",
            'Set auth.client_id and auth.tenant_id in team.toml (or ~/.rca/config.toml), or set auth.mode = "pat".',
        ).to_dict()["error"]
    else:
        try:
            user = cached_username(cfg)
            signed_in = user is not None
        except RcaError as e:
            auth_error = e.to_dict()["error"]
    status = read_status(cfg)
    bug_type = cfg.bug_type or (status.get("bug_type") if status.get("bug_type_for") == f"{cfg.org_url}|{cfg.project}" else None)
    return {"signed_in": signed_in, "user": user, "auth_mode": cfg.auth_mode, "auth_error": auth_error,
            "org_url": cfg.org_url, "project": cfg.project, "configured": bool(cfg.org_url and cfg.project),
            "fields_ok": bool(status.get("fields_ok")), "current_pi": cfg.current_pi, "bug_type": bug_type,
            "tool_version": current_version()}


@guarded
def login(cfg: Config, complete: bool = False, auth_factory: Callable[[Config], TokenProvider] = TokenProvider) -> dict:
    if cfg.auth_mode == "pat":
        if not cfg._env.get(cfg.pat_env):
            cfg.pat()  # raises the standard no_pat RcaError
        return {"signed_in": True, "user": f"PAT ({cfg.pat_env})", "auth_mode": "pat"}
    return auth_factory(cfg).login(complete=complete)


@guarded
def options(cfg: Config, client: AdoClient) -> dict:
    accounts = client.list_accounts()
    projects = client.list_projects() if cfg.org_url else []
    return {"accounts": accounts, "projects": projects}


@guarded
def save_config(cfg: Config, org_url: str | None = None, project: str | None = None, fields: dict | None = None,
                current_pi: str | None = None, auth_mode: str | None = None,
                client_id: str | None = None, tenant_id: str | None = None) -> dict:
    path = _user_path(cfg)
    data = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    patch: dict = {}
    if org_url is not None:
        patch.setdefault("ado", {})["org_url"] = org_url.rstrip("/")
    if project is not None:
        patch.setdefault("ado", {})["project"] = project
    if fields:
        patch["fields"] = dict(fields)
    if current_pi is not None:
        patch.setdefault("git", {})["current_pi"] = current_pi
    if auth_mode is not None:
        patch.setdefault("auth", {})["mode"] = auth_mode
    if client_id is not None:
        patch.setdefault("auth", {})["client_id"] = client_id
    if tenant_id is not None:
        patch.setdefault("auth", {})["tenant_id"] = tenant_id
    data = merge(data, patch)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(data), encoding="utf-8")
    if org_url is not None or project is not None:
        write_status(cfg, bug_type=None, bug_type_for=None, fields_ok=False)
    return {"path": str(path), "saved": patch}
