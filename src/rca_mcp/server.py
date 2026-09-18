from __future__ import annotations

from pathlib import Path

try:  # mcp >= 2.x renamed FastMCP
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP

from rca_core.ado_client import AdoClient
from rca_core.config import DEFAULT_USER_PATH, Config, load_config
from rca_core.errors import RcaError
from rca_core.operations.classify import classify_op
from rca_core.operations.fetch import fetch
from rca_core.operations.fields import fields_op
from rca_core.operations.publish import publish
from rca_core.operations.setup import login, options, save_config, status
from rca_core.operations.trace import trace
from rca_core.session import build_client
from rca_core.update_check import current_version, newer_tag

USER_CONFIG: Path = DEFAULT_USER_PATH
mcp = FastMCP("ado-rca")


def _ctx() -> tuple[Config, AdoClient]:
    cfg = load_config(user_path=USER_CONFIG)
    client, _auth = build_client(cfg)
    return cfg, client


@mcp.tool()
def rca_status() -> dict:
    """Is the tool ready? Returns signed_in/user, auth_mode, org_url/project, configured, fields_ok, current_pi, tool_version.
    Call first; if configured is false or signed_in is false, run the setup steps."""
    return status(load_config(user_path=USER_CONFIG))


@mcp.tool()
def rca_login(complete: bool = False) -> dict:
    """Sign in to Azure DevOps with the work account (opens the browser). If the result has device_code_message,
    show it to the user and call rca_login(complete=True) once they confirm they signed in."""
    return login(load_config(user_path=USER_CONFIG), complete=complete)


@mcp.tool()
def rca_setup_options() -> dict:
    """Organizations the signed-in user can see and, once org_url is saved, the projects in it."""
    try:
        cfg, client = _ctx()
    except RcaError as e:
        return e.to_dict()
    return options(cfg, client)


@mcp.tool()
def rca_save_config(org_url: str | None = None, project: str | None = None, fields: dict[str, str] | None = None,
                    current_pi: str | None = None, auth_mode: str | None = None,
                    client_id: str | None = None, tenant_id: str | None = None) -> dict:
    """Persist setup choices to ~/.rca/config.toml. Never pass secrets. client_id/tenant_id are the team's
    Entra app registration (public identifiers, not secrets)."""
    return save_config(load_config(user_path=USER_CONFIG), org_url=org_url, project=project, fields=fields,
                       current_pi=current_pi, auth_mode=auth_mode, client_id=client_id, tenant_id=tenant_id)


@mcp.tool()
def rca_fetch(bug: str = "", pr_id: int | None = None, cwd: str | None = None) -> dict:
    """Fetch the Bug and its fix diff. `bug` may be an id, a work item URL, or empty to infer it from the current git
    branch in `cwd` (pass the user's working directory). Fix source order: pr_id, PR linked to the Bug, PR of the current
    branch, then the local branch diff. Returns bug, pr, source, repo, base/head, files (capped), truncated, resolved."""
    try:
        cfg, client = _ctx()
    except RcaError as e:
        return e.to_dict()
    out = fetch(bug or None, cfg, client, pr_id=pr_id, cwd=Path(cwd) if cwd else None)
    if "error" not in out:
        out["update_available"] = newer_tag(cfg.repo_url, current_version())
        out["tool_version"] = current_version()
    return out


@mcp.tool()
def rca_trace(bug_id: int) -> dict:
    """Blame the pre-fix lines of a fetched bug to find culprit commits; for each, the merging PR, linked work items,
    parent chain (Task -> Story -> Feature), release branches containing it, and earliest version. Requires rca_fetch first."""
    try:
        cfg, client = _ctx()
    except RcaError as e:
        return e.to_dict()
    return trace(bug_id, cfg, client)


@mcp.tool()
def rca_classify(bug_id: int) -> dict:
    """Propose the bug classification (Legacy Bug / Feature Bug / Non-Feature Bug) from the cached trace,
    with confidence, reason and needs_confirmation."""
    try:
        cfg, client = _ctx()
    except RcaError as e:
        return e.to_dict()
    return classify_op(bug_id, cfg, client=client)


@mcp.tool()
def rca_fields(auto_map: bool = True) -> dict:
    """List the Bug work item type's fields (reference name, display name, type, allowed values) and report
    any RCA section whose configured field is missing, with a suggested match."""
    try:
        cfg, client = _ctx()
    except RcaError as e:
        return e.to_dict()
    return fields_op(cfg, client, auto_map=auto_map)


@mcp.tool()
def rca_publish(bug_id: int, sections: dict[str, str], dry_run: bool = True) -> dict:
    """Write RCA sections to the Bug's mapped fields. `sections` keys: summary, root_cause, impact, previous_versions,
    related_ids, classification, preventive_action, lesson_learned, analysis_method, fix_description, impacted_area,
    culprit_commit, why_missed. dry_run=True returns the PATCH body without writing. Only call with dry_run=False after
    the user has confirmed the draft."""
    try:
        cfg, client = _ctx()
    except RcaError as e:
        return e.to_dict()
    return publish(bug_id, sections, cfg, client, dry_run=dry_run)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
