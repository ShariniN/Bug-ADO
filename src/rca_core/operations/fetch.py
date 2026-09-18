from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from rca_core.ado_client import AdoClient
from rca_core.ado_history import AdoHistory
from rca_core.cache import write_cache
from rca_core.config import Config
from rca_core.diffparse import cap_hunks, parse_unified_diff
from rca_core.errors import RcaError, guarded
from rca_core.git_forensics import GitRepo, find_repo_root
from rca_core.models import BugInfo, PullRequestInfo, to_dict
from rca_core.resolve import resolve_bug

FETCH_CAP_BYTES = 6000
_TAGS = re.compile(r"<[^>]+>")
_EXTRA_HINTS = ("environment", "client", "customer", "tenant", "severity", "priority", "foundin", "found in", "build")


def _plain(html: str) -> str:
    return _TAGS.sub("", html or "").replace("&nbsp;", " ").strip()


def bug_from_work_item(w: dict) -> BugInfo:
    f = w.get("fields", {})
    extra = {k: str(v) for k, v in f.items()
             if any(h in k.lower() for h in _EXTRA_HINTS) and isinstance(v, (str, int, float)) and str(v)}
    return BugInfo(
        id=int(w["id"]), title=f.get("System.Title", ""), state=f.get("System.State", ""),
        area_path=f.get("System.AreaPath", ""), iteration_path=f.get("System.IterationPath", ""),
        repro_steps=_plain(f.get("Microsoft.VSTS.TCM.ReproSteps", ""))[:2000],
        description=_plain(f.get("System.Description", ""))[:2000],
        tags=[t.strip() for t in f.get("System.Tags", "").split(";") if t.strip()],
        extra=extra, pr_ids=AdoClient.linked_pr_ids(w),
    )


def _pr_diff(pr: PullRequestInfo, hist: AdoHistory, client: AdoClient) -> tuple[str, str, str, bool]:
    """(base, head, diff_text, paths_truncated) for a PR, using the merge commit when the source commit no longer exists."""
    head = pr.source_sha
    if head and hist.commit_exists(head) and pr.target_sha:
        base = hist.merge_base(pr.target_sha, head)
        if base:
            return base, head, hist.diff(base, head), hist.paths_truncated
    if pr.merge_sha:
        info = client.get_commit(pr.repo_id, pr.merge_sha)
        if info["parents"]:
            return info["parents"][0], pr.merge_sha, hist.diff(info["parents"][0], pr.merge_sha), hist.paths_truncated
    raise RcaError("history_unavailable", f"Azure DevOps has neither the source nor the merge commit of PR {pr.id}.",
                   "Check the PR still exists and was pushed to this project; otherwise run /rca from your fix branch.")


def _origin_repo_id(g: GitRepo, client: AdoClient) -> str | None:
    url = g.run("config", "--get", "remote.origin.url", check=False).strip()
    name = url.rstrip("/").split("/")[-1].removesuffix(".git") if url else ""
    if not name:
        return None
    for r in client.list_repositories():
        if r["name"].lower() == name.lower():
            return r["id"]
    return None


@guarded
def fetch(bug: str | int | None, cfg: Config, client: AdoClient, pr_id: int | None = None, cwd: Path | None = None,
          history_factory: Callable[..., AdoHistory] = AdoHistory, repo_factory: Callable[..., GitRepo] = GitRepo) -> dict:
    cwd = Path.cwd() if cwd is None else Path(cwd)
    resolved = resolve_bug(bug, client, cwd)
    bug_id = resolved["bug_id"]
    info = bug_from_work_item(client.get_work_item(bug_id))
    pr: PullRequestInfo | None = None
    root = find_repo_root(cwd)

    if pr_id is not None:
        repo_id = next((c[0] for c in info.pr_ids if c[1] == pr_id), None) or client.pr_repo_id(pr_id)
        pr = client.get_pull_request(repo_id, pr_id)
    elif info.pr_ids:
        pr = client.get_pull_request(*info.pr_ids[-1])
    elif resolved.get("pr_id"):
        pr = client.get_pull_request(resolved["repo_id"], resolved["pr_id"])
    elif root is not None:
        branch = repo_factory(root).current_branch()
        prs = client.find_prs_by_source_branch(branch)
        if prs:
            pr = client.get_pull_request(prs[0]["repo_id"], prs[0]["id"])

    if pr is not None:
        hist = history_factory(client, pr.repo_id)
        base_sha, head_sha, diff_text, paths_truncated = _pr_diff(pr, hist, client)
        source, repo_name, repo_id = "pr", pr.repo_name, pr.repo_id
    else:
        if root is None:
            raise RcaError("no_fix_source", f"Bug {bug_id} has no linked PR and {cwd} is not a git repository.",
                           "Link the fix PR to the Bug, pass pr_id, or run /rca from inside the repo on your fix branch.")
        g = repo_factory(root)
        branch = g.current_branch()
        if branch == cfg.default_target_branch:
            raise RcaError("no_fix_source", f"Bug {bug_id} has no linked PR and the current branch is '{branch}'.",
                           "Check out your fix branch (or pass pr_id) and run /rca again.")
        g.fetch()
        target = next((t for t in (f"origin/{cfg.default_target_branch}", cfg.default_target_branch) if g.has_ref(t)), None)
        if target is None:
            raise RcaError("no_fix_source", f"Neither origin/{cfg.default_target_branch} nor {cfg.default_target_branch} exists in {root}.",
                           "Fetch the repo or set git.default_target_branch in ~/.rca/config.toml.")
        head_sha = g.rev_parse("HEAD")
        base_sha = g.merge_base(target, head_sha)
        diff_text = g.diff(base_sha, head_sha)
        source, repo_name, repo_id = "branch", root.name, _origin_repo_id(g, client)
        paths_truncated = False

    files = parse_unified_diff(diff_text)
    capped, truncated = cap_hunks(files, FETCH_CAP_BYTES)
    truncated = truncated or paths_truncated
    full = {"bug_id": bug_id, "bug": to_dict(info), "pr": to_dict(pr) if pr else None, "source": source,
            "repo": repo_name, "repo_id": repo_id, "resolved": resolved, "base_sha": base_sha, "head_sha": head_sha,
            "files_full": to_dict(files)}
    path = write_cache(cfg, bug_id, {**full, "trace": None, "pi": None})
    return {**{k: v for k, v in full.items() if k != "files_full"}, "files": to_dict(capped),
            "truncated": truncated, "cache_path": str(path)}
