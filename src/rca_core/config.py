from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Mapping

from rca_core.errors import RcaError

DEFAULT_USER_PATH = Path.home() / ".rca" / "config.toml"


def merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class Config:
    org_url: str
    project: str
    pat_env: str
    release_branch_pattern: str
    legacy_cutoff: str
    current_pi: str
    default_target_branch: str
    repo_url: str
    auth_mode: str = "browser"
    client_id: str = ""
    tenant_id: str = ""
    persist_tokens: bool = True
    bug_type: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    home: Path = field(default_factory=lambda: Path.home() / ".rca")
    _env: Mapping[str, str] = field(default_factory=dict, repr=False)

    @property
    def cache_dir(self) -> Path:
        return self.home / "cache"

    @property
    def token_cache_path(self) -> Path:
        return self.home / "msal_cache.bin"

    def pat(self) -> str:
        value = self._env.get(self.pat_env, "")
        if not value:
            raise RcaError(
                "no_pat",
                f"Environment variable {self.pat_env} is not set.",
                f"Create an Azure DevOps PAT with Work Items (read/write) and Code (read) scopes and set {self.pat_env}.",
            )
        return value


def _team_defaults() -> dict[str, Any]:
    text = resources.files("rca_core").joinpath("defaults/team.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)


def load_config(user_path: Path | None = None, env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    data = _team_defaults()
    path = DEFAULT_USER_PATH if user_path is None else user_path
    if path.exists():
        data = merge(data, tomllib.loads(path.read_text(encoding="utf-8")))
    ado, git, tool, auth = data.get("ado", {}), data.get("git", {}), data.get("tool", {}), data.get("auth", {})
    return Config(
        org_url=ado.get("org_url", "").rstrip("/"),
        project=ado.get("project", ""),
        pat_env=ado.get("pat_env", "ADO_PAT"),
        bug_type=ado.get("bug_type", ""),
        release_branch_pattern=git.get("release_branch_pattern", r"release/(\d+\.\d+)"),
        legacy_cutoff=str(git.get("legacy_cutoff", "9.6")),
        current_pi=git.get("current_pi", ""),
        default_target_branch=git.get("default_target_branch", "main"),
        repo_url=tool.get("repo_url", ""),
        auth_mode=auth.get("mode", "browser"),
        client_id=auth.get("client_id", ""),
        tenant_id=auth.get("tenant_id", ""),
        persist_tokens=bool(auth.get("persist_tokens", True)),
        fields=dict(data.get("fields", {})),
        home=path.parent,
        _env=env,
    )
