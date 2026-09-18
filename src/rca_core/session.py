from __future__ import annotations

from typing import Any, Callable

from rca_core.ado_client import AdoClient, RequestsTransport
from rca_core.auth import TokenProvider
from rca_core.config import Config


def build_client(cfg: Config, app_factory: Callable[[Config, Any], Any] | None = None) -> tuple[AdoClient, TokenProvider | None]:
    """PAT mode: Basic auth from the env var. Browser mode: lazy Bearer tokens (first request raises not_signed_in if needed)."""
    if cfg.auth_mode == "pat":
        return AdoClient(cfg.org_url, cfg.project, RequestsTransport(pat=cfg.pat())), None
    auth = TokenProvider(cfg, **({"app_factory": app_factory} if app_factory else {}))
    return AdoClient(cfg.org_url, cfg.project, RequestsTransport(token_provider=auth.token, on_unauthorized=auth.invalidate)), auth
