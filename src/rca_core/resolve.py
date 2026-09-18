from __future__ import annotations

import re
from pathlib import Path

from rca_core.ado_client import AdoClient
from rca_core.errors import RcaError
from rca_core.git_forensics import GitRepo, find_repo_root

_URL_ID = re.compile(r"/_workitems/edit/(\d+)", re.IGNORECASE)
_BRANCH_ID = re.compile(r"(?<!\d)(\d{3,7})(?!\d)")


def _hit(bug_id: int, how: str, pr_id: int | None = None, repo_id: str | None = None) -> dict:
    return {"bug_id": bug_id, "how": how, "pr_id": pr_id, "repo_id": repo_id}


def resolve_bug(arg: str | int | None, client: AdoClient, cwd: Path | None) -> dict:
    s = "" if arg is None else str(arg).strip()
    if s.isdigit():
        return _hit(int(s), "argument")
    if m := _URL_ID.search(s):
        return _hit(int(m.group(1)), "url")
    if s:
        raise RcaError("bug_not_resolved", f"'{s}' is not a bug id or a work item URL.",
                       "Pass the numeric Bug ID or its Azure DevOps URL.")
    root = find_repo_root(cwd)
    if root is None:
        raise RcaError("bug_not_resolved", "No bug id given and the current folder is not a git repository.",
                       "Pass the Bug ID, or run /rca from inside the repo while on your fix branch.")
    branch = GitRepo(root).current_branch()
    for pr in client.find_prs_by_source_branch(branch):
        info = client.get_pull_request(pr["repo_id"], pr["id"])
        bugs = [w for w in info.work_items if w.type.lower() == "bug"]
        if bugs:
            return _hit(bugs[0].id, f"PR {pr['id']} for branch {branch}", pr["id"], pr["repo_id"])
    for m in _BRANCH_ID.finditer(branch):
        try:
            w = client.get_work_item(int(m.group(1)))
        except RcaError as e:
            if e.code in ("bug_not_found", "not_found"):
                continue
            raise
        if w.get("fields", {}).get("System.WorkItemType", "").lower() == "bug":
            return _hit(int(m.group(1)), f"id in branch name {branch}")
    raise RcaError("bug_not_resolved", f"Could not infer a Bug from branch '{branch}'.",
                   "Pass the Bug ID explicitly, or link the Bug to the PR for this branch.")
