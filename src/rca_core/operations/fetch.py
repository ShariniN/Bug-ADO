from __future__ import annotations

import re
from typing import Callable

from rca_core.ado_client import AdoClient
from rca_core.cache import write_cache
from rca_core.config import Config
from rca_core.diffparse import cap_hunks, parse_unified_diff
from rca_core.errors import RcaError, guarded
from rca_core.git_forensics import GitRepo
from rca_core.models import BugInfo, PullRequestInfo, to_dict

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


def _resolve_target(repo: GitRepo, cfg: Config) -> str:
    for ref in (f"origin/{cfg.default_target_branch}", cfg.default_target_branch):
        if repo.has_ref(ref):
            return ref
    raise RcaError("repo_not_cloned", f"Neither origin/{cfg.default_target_branch} nor {cfg.default_target_branch} exists in {repo.path}.",
                   "Fetch the repo or set git.default_target_branch in ~/.rca/config.toml.")


@guarded
def fetch(bug_id: int, cfg: Config, client: AdoClient, pr_id: int | None = None, branch: str | None = None,
          repo: str | None = None, repo_factory: Callable[..., GitRepo] = GitRepo) -> dict:
    bug = bug_from_work_item(client.get_work_item(bug_id))
    pr: PullRequestInfo | None = None
    source = "branch"

    if branch is None:
        candidates = bug.pr_ids
        if pr_id is not None:
            matching = [c for c in candidates if c[1] == pr_id]
            if matching:
                candidates = matching
            elif candidates:
                candidates = [(candidates[0][0], pr_id)]
            elif repo:
                candidates = [(repo, pr_id)]
        if not candidates:
            raise RcaError("no_linked_pr", f"Bug {bug_id} has no linked pull request.",
                           "Link the PR to the Bug in Azure DevOps, or pass pr_id together with repo=<name>, or pass the branch name and repo to use the local branch instead.")
        repo_id, chosen = candidates[-1]
        pr = client.get_pull_request(repo_id, chosen)
        repo_name = pr.repo_name
        source = "pr"
    else:
        if not repo:
            raise RcaError("repo_not_configured", "Branch mode needs the repo name.",
                           "Pass repo=<name as in [repos] of ~/.rca/config.toml>.")
        repo_name = repo

    g = repo_factory(cfg.repo_path(repo_name))
    g.fetch()
    if pr is not None:
        head_sha, base_sha = pr.source_sha, pr.target_sha
        if not g.has_ref(head_sha):
            # Source branch deleted after a squash/rebase merge (ADO default): diff the merge commit itself.
            if pr.merge_sha and g.has_ref(pr.merge_sha):
                head_sha = pr.merge_sha
                base_sha = g.rev_parse(f"{pr.merge_sha}^1")
            else:
                raise RcaError("repo_not_cloned", f"Commit {head_sha[:8]} from PR {pr.id} is not in the local clone.",
                               f"Run 'git fetch origin' in {g.path} (the PR branch may have been deleted; fetch refs/pull/{pr.id}/merge).")
        else:
            base_sha = g.merge_base(base_sha, head_sha)
    else:
        target = _resolve_target(g, cfg)
        if not g.has_ref(branch):
            raise RcaError("repo_not_cloned", f"Branch '{branch}' does not exist in the local clone at {g.path}.",
                           f"Run 'git fetch origin' in {g.path} or check the branch name (try origin/{branch}).")
        head_sha = g.rev_parse(branch)
        base_sha = g.merge_base(target, head_sha)

    files = parse_unified_diff(g.diff(base_sha, head_sha))
    capped, truncated = cap_hunks(files, FETCH_CAP_BYTES)

    full = {"bug": to_dict(bug), "pr": to_dict(pr) if pr else None, "source": source, "repo": repo_name,
            "base_sha": base_sha, "head_sha": head_sha, "files_full": to_dict(files)}
    path = write_cache(cfg, bug_id, full)
    return {**{k: v for k, v in full.items() if k != "files_full"},
            "files": to_dict(capped), "truncated": truncated, "cache_path": str(path)}
