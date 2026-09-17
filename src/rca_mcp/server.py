from __future__ import annotations

from pathlib import Path

try:  # mcp >= 2.x renamed FastMCP
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP

from rca_core.ado_client import AdoClient, RequestsTransport
from rca_core.config import DEFAULT_USER_PATH, Config, load_config
from rca_core.errors import RcaError
from rca_core.operations.classify import classify_op
from rca_core.operations.fetch import fetch
from rca_core.operations.fields import fields_op
from rca_core.operations.publish import publish
from rca_core.operations.trace import trace
from rca_core.update_check import current_version, newer_tag

USER_CONFIG: Path = DEFAULT_USER_PATH
mcp = FastMCP("ado-rca")


def _ctx() -> tuple[Config, AdoClient]:
    cfg = load_config(user_path=USER_CONFIG)
    return cfg, AdoClient(cfg.org_url, cfg.project, RequestsTransport(cfg.pat()))


@mcp.tool()
def rca_fetch(bug_id: int, pr_id: int | None = None, branch: str | None = None, repo: str | None = None) -> dict:
    """Fetch an Azure DevOps Bug, its linked PR (or a local branch when branch+repo are given), and the fix diff as hunks.
    Returns bug fields, PR info, base/head SHAs, changed files with hunks (capped), and update_available."""
    try:
        cfg, client = _ctx()
    except RcaError as e:
        return e.to_dict()
    out = fetch(bug_id, cfg, client, pr_id=pr_id, branch=branch, repo=repo)
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
        cfg, _ = _ctx()
    except RcaError as e:
        return e.to_dict()
    return classify_op(bug_id, cfg)


@mcp.tool()
def rca_fields() -> dict:
    """List the Bug work item type's fields (reference name, display name, type, allowed values) and report
    any RCA section whose configured field is missing, with a suggested match."""
    try:
        cfg, client = _ctx()
    except RcaError as e:
        return e.to_dict()
    return fields_op(cfg, client)


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
